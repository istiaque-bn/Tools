from django import forms

from .models import AbbreviationEntry
from .models import AbbreviationProfile, DocumentProcessingSession


class DictionarySearchForm(forms.Form):
    q = forms.CharField(required=False, max_length=200, label="Search")
    service = forms.CharField(required=False, max_length=50)
    status = forms.ChoiceField(required=False, choices=(("", "All statuses"), *AbbreviationEntry.Status.choices))
    ambiguous = forms.NullBooleanField(required=False)


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
