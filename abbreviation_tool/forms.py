from django import forms

from .models import AbbreviationEntry, Feedback
from .models import AbbreviationProfile, DocumentProcessingSession


class DictionarySearchForm(forms.Form):
    q = forms.CharField(required=False, max_length=200, label="Search")
    service = forms.CharField(required=False, max_length=50)
    status = forms.ChoiceField(required=False, choices=(("", "All statuses"), *AbbreviationEntry.Status.choices))
    ambiguous = forms.NullBooleanField(required=False)


class AbbreviationEntryForm(forms.ModelForm):
    class Meta:
        model = AbbreviationEntry
        fields = ("abbreviation", "full_form")
        help_texts = {"full_form": "For multiple meanings, add each full form as a separate entry using the same abbreviation."}

    def clean_full_form(self):
        full_form = self.cleaned_data["full_form"]
        if " / " in full_form:
            raise forms.ValidationError("Add each meaning as a separate entry instead of separating full forms with '/'.")
        return full_form

    def clean(self):
        cleaned = super().clean()
        short = AbbreviationEntry.normalize(cleaned.get("abbreviation", ""))
        full = AbbreviationEntry.normalize(cleaned.get("full_form", ""))
        duplicate = AbbreviationEntry.objects.filter(normalized_abbreviation=short, normalized_full_form=full)
        if self.instance.pk:
            duplicate = duplicate.exclude(pk=self.instance.pk)
        if short and full and duplicate.exists():
            raise forms.ValidationError("This abbreviation and full-form pair already exists.")
        return cleaned


class DictionaryImportForm(forms.Form):
    file = forms.FileField(help_text="CSV or XLSX with abbreviation and full_form columns (maximum 2 MB).")

    def clean_file(self):
        upload = self.cleaned_data["file"]
        if upload.size > 2 * 1024 * 1024:
            raise forms.ValidationError("The import file must be 2 MB or smaller.")
        if not upload.name.lower().endswith((".csv", ".xlsx")):
            raise forms.ValidationError("Upload a CSV or XLSX file.")
        return upload


class FeedbackForm(forms.ModelForm):
    class Meta:
        model = Feedback
        fields = ("name", "email", "message")
        widgets = {"message": forms.Textarea(attrs={"rows": 5})}


class DocumentUploadForm(forms.Form):
    GLOSSARY_CHOICES = (("none", "Do not generate"), ("preview", "Preview only"), ("separate", "Download separately"), ("insert_end", "Insert at end of document"), ("bookmark", "Insert at configured bookmark"))
    operation_type = forms.ChoiceField(choices=DocumentProcessingSession.Operation.choices, widget=forms.RadioSelect)
    profile = forms.ModelChoiceField(queryset=AbbreviationProfile.objects.none())
    pdf_file = forms.FileField(label="DOCX document")
    replacement_policy = forms.ChoiceField(choices=DocumentProcessingSession.Policy.choices, initial=DocumentProcessingSession.Policy.DEFINE_FIRST)
    include_tables = forms.BooleanField(required=False, initial=True)
    include_headers_footers = forms.BooleanField(required=False)
    include_footnotes_endnotes = forms.BooleanField(required=False)
    case_sensitive = forms.BooleanField(required=False)
    high_confidence_only = forms.BooleanField(required=False)
    glossary_mode = forms.ChoiceField(choices=GLOSSARY_CHOICES, initial="none", required=False)
    glossary_bookmark = forms.CharField(required=False, max_length=100)

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("glossary_mode") == "bookmark" and not cleaned.get("glossary_bookmark"):
            self.add_error("glossary_bookmark", "Enter the Word bookmark where the glossary should be inserted.")
        return cleaned

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["profile"].queryset = AbbreviationProfile.objects.filter(active=True)

    def clean_pdf_file(self):
        from .validators import validate_docx

        upload = self.cleaned_data["pdf_file"]
        self.inspection = validate_docx(upload)
        return upload


class QuickProcessForm(forms.Form):
    operation_type = forms.ChoiceField(choices=DocumentProcessingSession.Operation.choices, widget=forms.RadioSelect, initial=DocumentProcessingSession.Operation.ABBREVIATE)
    docx_file = forms.FileField(label="DOCX document")

    def clean_docx_file(self):
        from .validators import validate_docx
        upload = self.cleaned_data["docx_file"]
        self.inspection = validate_docx(upload)
        return upload


class PowerPointProcessForm(forms.Form):
    operation_type = forms.ChoiceField(choices=DocumentProcessingSession.Operation.choices, widget=forms.RadioSelect, initial=DocumentProcessingSession.Operation.ABBREVIATE)
    presentation_file = forms.FileField(label="PowerPoint presentation")

    def clean_presentation_file(self):
        upload = self.cleaned_data["presentation_file"]
        name = upload.name.lower()
        if name.endswith(".ppt"):
            raise forms.ValidationError("Legacy .ppt files cannot be safely edited. Open the file in PowerPoint or LibreOffice and save it as .pptx first.")
        if not name.endswith(".pptx"):
            raise forms.ValidationError("Upload a PowerPoint .pptx file.")
        if upload.size < 1:
            raise forms.ValidationError("The presentation is empty.")
        return upload
