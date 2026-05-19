"""Seed KNEC default strands and sub-strands for the most common CBC subjects.

The data is keyed by *subject name* (case-insensitive match against
``academics.Subject.name``) because schools may run on different ``code``
schemes. The migration walks every existing Subject row across every
School and creates strands only when both the subject and grade level
match an entry in ``KNEC_DEFAULTS``.

The migration is fully idempotent — if a strand with the same
(subject, grade_level, name) already exists, it is left alone and any
declared sub-strands are still upserted into it. Re-running this
migration after a flush is safe.

Coverage in this v1 seed:
* English – Grade 4 & Grade 7 (PP1 to JSS varies; we seed two
  representative levels so the catalog is usable immediately).
* Kiswahili – Grade 4 & Grade 7
* Mathematics – Grade 4 & Grade 7
* Integrated Science / Science & Technology – Grade 4 & Grade 7
* Social Studies – Grade 4 & Grade 7
* CRE – Grade 4 & Grade 7
* Creative Arts – Grade 4 & Grade 7

Schools that need additional grades or strands can extend the catalog
through the admin / strand CRUD UI without touching this migration.
"""
from django.db import migrations


KNEC_DEFAULTS = {
    # subject_name (lower) → list of (grade_level, strand_name, [sub_strands])
    "english": [
        ("Grade 4", "Listening and Speaking", [
            "Pronunciation",
            "Conversation skills",
            "Listening comprehension",
        ]),
        ("Grade 4", "Reading", [
            "Reading aloud",
            "Reading comprehension",
            "Vocabulary in context",
        ]),
        ("Grade 4", "Writing", [
            "Penmanship & spelling",
            "Guided composition",
            "Punctuation",
        ]),
        ("Grade 4", "Language Use", [
            "Nouns and pronouns",
            "Verb tenses",
            "Sentence structure",
        ]),
        ("Grade 7", "Listening and Speaking", [
            "Oral presentation",
            "Active listening",
        ]),
        ("Grade 7", "Reading", [
            "Intensive reading",
            "Extensive reading",
        ]),
        ("Grade 7", "Writing", [
            "Functional writing",
            "Creative writing",
        ]),
        ("Grade 7", "Grammar", [
            "Word classes",
            "Sentence types",
        ]),
    ],
    "kiswahili": [
        ("Grade 4", "Kusikiliza na Kuzungumza", [
            "Matamshi bora",
            "Mazungumzo",
        ]),
        ("Grade 4", "Kusoma", [
            "Ufahamu",
            "Msamiati",
        ]),
        ("Grade 4", "Kuandika", [
            "Insha rahisi",
            "Imla",
        ]),
        ("Grade 4", "Sarufi", [
            "Aina za maneno",
            "Sentensi",
        ]),
        ("Grade 7", "Kusikiliza na Kuzungumza", [
            "Hotuba",
            "Mahojiano",
        ]),
        ("Grade 7", "Kusoma", [
            "Ufahamu wa kina",
            "Vitabu vya hadithi",
        ]),
        ("Grade 7", "Kuandika", [
            "Insha za kimaelezo",
            "Insha za masimulizi",
        ]),
        ("Grade 7", "Sarufi", [
            "Tungo",
            "Vitenzi",
        ]),
    ],
    "mathematics": [
        ("Grade 4", "Numbers", [
            "Whole numbers",
            "Fractions",
            "Decimals",
        ]),
        ("Grade 4", "Measurement", [
            "Length",
            "Mass",
            "Time",
            "Money",
        ]),
        ("Grade 4", "Geometry", [
            "Lines and angles",
            "Plane figures",
        ]),
        ("Grade 4", "Data Handling", [
            "Tables and charts",
        ]),
        ("Grade 7", "Numbers", [
            "Integers",
            "Rational numbers",
        ]),
        ("Grade 7", "Algebra", [
            "Algebraic expressions",
            "Linear equations",
        ]),
        ("Grade 7", "Measurement", [
            "Area and volume",
            "Time, money and ratios",
        ]),
        ("Grade 7", "Geometry", [
            "Angles",
            "Geometric constructions",
        ]),
        ("Grade 7", "Data Handling", [
            "Statistics",
            "Probability",
        ]),
    ],
    "science and technology": [
        ("Grade 4", "Living Things", ["Plants", "Animals"]),
        ("Grade 4", "Environment", ["Weather", "Water"]),
        ("Grade 4", "Force and Energy", ["Force", "Light and sound"]),
        ("Grade 4", "Digital Technology", ["Digital devices"]),
    ],
    "integrated science": [
        ("Grade 7", "Living Things", ["Cell structure", "Classification"]),
        ("Grade 7", "Mixtures, Elements & Compounds", ["Mixtures", "Acids and bases"]),
        ("Grade 7", "Force and Energy", ["Force", "Energy transformations"]),
        ("Grade 7", "Earth and Space", ["Atmosphere", "Hydrosphere"]),
    ],
    "social studies": [
        ("Grade 4", "Natural and Built Environments", ["Map work", "Resources"]),
        ("Grade 4", "Citizenship", ["Rights and responsibilities"]),
        ("Grade 4", "Culture and Heritage", ["Communities of Kenya"]),
        ("Grade 7", "People and Population", ["Population distribution"]),
        ("Grade 7", "Resources and Economic Activities", ["Agriculture", "Industries"]),
        ("Grade 7", "Political Systems and Governance", ["Government structure"]),
    ],
    "cre": [
        ("Grade 4", "Creation", ["God the creator"]),
        ("Grade 4", "The Bible", ["Bible stories"]),
        ("Grade 4", "The Life of Jesus Christ", ["Jesus' teachings"]),
        ("Grade 4", "Christian Values", ["Honesty", "Love"]),
        ("Grade 7", "Creation", ["Stewardship"]),
        ("Grade 7", "The Bible", ["The Old Testament", "The New Testament"]),
        ("Grade 7", "The Life of Jesus Christ", ["Miracles", "Parables"]),
        ("Grade 7", "Christian Living Today", ["Christian values"]),
    ],
    "creative arts": [
        ("Grade 4", "Visual Arts", ["Drawing", "Painting"]),
        ("Grade 4", "Performing Arts", ["Music", "Dance"]),
        ("Grade 7", "Visual Arts", ["Picture making", "Graphic design"]),
        ("Grade 7", "Performing Arts", ["Music composition", "Drama"]),
    ],
}


def seed_strands(apps, schema_editor):
    Subject = apps.get_model("academics", "Subject")
    Strand = apps.get_model("cbc", "Strand")
    SubStrand = apps.get_model("cbc", "SubStrand")

    for subject in Subject.objects.all():
        key = subject.name.strip().lower()
        entries = KNEC_DEFAULTS.get(key)
        if not entries:
            continue
        for grade_level, strand_name, sub_strand_names in entries:
            strand, _ = Strand.objects.get_or_create(
                subject=subject,
                grade_level=grade_level,
                name=strand_name,
                defaults={"order": 0},
            )
            for index, sub_name in enumerate(sub_strand_names):
                SubStrand.objects.get_or_create(
                    strand=strand,
                    name=sub_name,
                    defaults={"order": index},
                )


def unseed_strands(apps, schema_editor):
    """Reverse migration intentionally narrow: delete only the seeded rows
    we can recognise by (grade_level, name)."""
    Strand = apps.get_model("cbc", "Strand")
    seeded_pairs = {
        (grade_level, strand_name)
        for entries in KNEC_DEFAULTS.values()
        for grade_level, strand_name, _subs in entries
    }
    qs = Strand.objects.all()
    to_delete = [s.pk for s in qs if (s.grade_level, s.name) in seeded_pairs]
    Strand.objects.filter(pk__in=to_delete).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("cbc", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_strands, unseed_strands),
    ]
