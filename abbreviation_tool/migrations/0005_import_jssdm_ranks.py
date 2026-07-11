from django.db import migrations


RANKS = {
    "Army": (("FM", "Field Marshal"), ("Gen", "General"), ("Lt Gen", "Lieutenant General"), ("Maj Gen", "Major General"), ("Brig Gen", "Brigadier General"), ("Col", "Colonel"), ("Lt Col", "Lieutenant Colonel"), ("Maj", "Major"), ("Capt", "Captain"), ("Lt", "Lieutenant"), ("2Lt", "Second Lieutenant"), ("MWO", "Master Warrant Officer"), ("SWO", "Senior Warrant Officer"), ("WO", "Warrant Officer"), ("Sgt", "Sergeant"), ("Cpl", "Corporal"), ("Lcpl", "Lance Corporal"), ("Snk", "Sainik"), ("Sep", "Sepoy"), ("GC", "Gentleman Cadet"), ("GWC", "Gentle Woman Cadet"), ("NC(E)", "Non-Combatants (Enrolled)"), ("NC(U)", "Non-Combatants (Unenrolled)"), ("Offr Cdt", "Officer Cadet"), ("Rect", "Recruit")),
    "Navy": (("AF", "Admiral of the Fleet"), ("Adm", "Admiral"), ("V Adm", "Vice Admiral"), ("R Adm", "Rear Admiral"), ("Cdre", "Commodore"), ("Capt", "Captain"), ("Cdr", "Commander"), ("Lt Cdr", "Lieutenant Commander"), ("Lt", "Lieutenant"), ("S Lt", "Sub Lieutenant"), ("Ag S Lt", "Acting Sub Lieutenant"), ("Mid", "Midshipman"), ("Offr Cdt", "Officer Cadet"), ("MCPO", "Master Chief Petty Officer"), ("SCPO", "Senior Chief Petty Officer"), ("CPO", "Chief Petty Officer"), ("PO", "Petty Officer"), ("LS", "Leading Seaman"), ("AB", "Able Seaman"), ("OD", "Ordinary Seaman")),
    "Air Force": (("Mshl of the AF", "Marshal of the Air Force"), ("Air Chf Mshl", "Air Chief Marshal"), ("Air Mshl", "Air Marshal"), ("AVM", "Air Vice Marshal"), ("Air Cdre", "Air Commodore"), ("Gp Capt", "Group Captain"), ("Wg Cdr", "Wing Commander"), ("Sqn Ldr", "Squadron Leader"), ("Flt Lt", "Flight Lieutenant"), ("Flg Offr", "Flying Officer"), ("Plt Offr", "Pilot Officer"), ("Offr Cdt", "Officer Cadet"), ("MWO", "Master Warrant Officer"), ("SWO", "Senior Warrant Officer"), ("WO", "Warrant Officer"), ("Sgt", "Sergeant"), ("Cpl", "Corporal"), ("LAC", "Leading Aircraftmen"), ("AC 1", "Aircraftmen 1"), ("AC 2", "Aircraftmen 2"), ("Appr", "Apprentice"), ("Rect", "Recruits")),
}


def import_ranks(apps, schema_editor):
    Entry = apps.get_model("abbreviation_tool", "AbbreviationEntry")
    Profile = apps.get_model("abbreviation_tool", "AbbreviationProfile")
    general = Profile.objects.filter(name="General").first()
    for service, ranks in RANKS.items():
        profile = Profile.objects.filter(name=service).first()
        for abbreviation, full_form in ranks:
            normalized_abbreviation = " ".join(abbreviation.casefold().split())
            normalized_full_form = " ".join(full_form.casefold().split())
            entry, created = Entry.objects.get_or_create(
                normalized_abbreviation=normalized_abbreviation,
                normalized_full_form=normalized_full_form,
                defaults={"abbreviation": abbreviation, "full_form": full_form, "service": service, "source_name": "JSSDM 2022", "source_section": "Section 16, Annex 16C", "source_page": 456},
            )
            if not created:
                services = {value.strip() for value in entry.service.split("/") if value.strip()}
                services.add(service)
                entry.service = " / ".join(sorted(services))
                if "Annex 16C" not in entry.source_section:
                    entry.source_section = (entry.source_section + "; Section 16, Annex 16C").strip("; ")
                entry.save(update_fields=("service", "source_section"))
            if general:
                entry.profiles.add(general)
            if profile:
                entry.profiles.add(profile)


class Migration(migrations.Migration):
    dependencies = [("abbreviation_tool", "0004_assign_existing_users")]
    operations = [migrations.RunPython(import_ranks, migrations.RunPython.noop)]
