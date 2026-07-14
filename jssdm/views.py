import fitz
from accounts.decorators import user_required
from django.db.models import Q
from django.shortcuts import render

from .models import Abbreviation
from .parser import abbreviation_candidates


@user_required
def checker(request):
    context = {"database_count": Abbreviation.objects.count()}
    query = request.GET.get("q", "").strip()
    if query:
        context["query"] = query
        context["search_results"] = Abbreviation.objects.filter(
            Q(abbreviation__icontains=query) | Q(meaning__icontains=query)
        )[:100]

    if request.method == "POST":
        upload = request.FILES.get("pdf_file")
        try:
            if not upload or not upload.name.lower().endswith(".pdf"):
                raise ValueError("Choose a valid PDF file.")
            document = fitz.open(stream=upload.read(), filetype="pdf")
            text = "\n".join(page.get_text("text") for page in document)
            document.close()
            candidates = abbreviation_candidates(text)
            records = list(Abbreviation.objects.filter(abbreviation__in=candidates))
            by_abbreviation = {}
            for record in records:
                by_abbreviation.setdefault(record.abbreviation, []).append(
                    record.meaning
                )
            context.update(
                filename=upload.name,
                candidate_count=len(candidates),
                recognized=[
                    {"value": item, "meanings": by_abbreviation[item]}
                    for item in candidates
                    if item in by_abbreviation
                ],
                unknown=[item for item in candidates if item not in by_abbreviation],
            )
        except (ValueError, fitz.FileDataError) as exc:
            context["error"] = str(exc)
    return render(request, "jssdm/checker.html", context)
