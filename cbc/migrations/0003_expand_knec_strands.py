from django.db import IntegrityError, migrations


LOWER_PRIMARY = ["Grade 1", "Grade 2", "Grade 3"]
UPPER_PRIMARY = ["Grade 4", "Grade 5", "Grade 6"]
JSS = ["Grade 7", "Grade 8", "Grade 9"]


SUBJECT_CATALOG = {
    "english": {
        "name": "English",
        "code": "ENG",
        "aliases": ["english"],
        "groups": {
            "lower_primary": [
                ("Listening and Speaking", ["Pronunciation", "Conversation skills", "Listening comprehension"]),
                ("Reading", ["Reading aloud", "Reading comprehension", "Vocabulary in context"]),
                ("Writing", ["Handwriting and spelling", "Guided writing", "Punctuation"]),
                ("Language Use", ["Nouns and pronouns", "Verb use", "Simple sentences"]),
            ],
            "upper_primary": [
                ("Listening and Speaking", ["Pronunciation", "Conversation skills", "Listening comprehension"]),
                ("Reading", ["Reading aloud", "Reading comprehension", "Vocabulary in context"]),
                ("Writing", ["Penmanship and spelling", "Guided composition", "Punctuation"]),
                ("Language Use", ["Nouns and pronouns", "Verb tenses", "Sentence structure"]),
            ],
            "jss": [
                ("Listening and Speaking", ["Oral presentation", "Active listening"]),
                ("Reading", ["Intensive reading", "Extensive reading"]),
                ("Writing", ["Functional writing", "Creative writing"]),
                ("Grammar", ["Word classes", "Sentence types"]),
            ],
        },
    },
    "kiswahili": {
        "name": "Kiswahili",
        "code": "KIS",
        "aliases": ["kiswahili"],
        "groups": {
            "lower_primary": [
                ("Kusikiliza na Kuzungumza", ["Matamshi bora", "Mazungumzo"]),
                ("Kusoma", ["Ufahamu", "Msamiati"]),
                ("Kuandika", ["Insha rahisi", "Imla"]),
                ("Sarufi", ["Aina za maneno", "Sentensi"]),
            ],
            "upper_primary": [
                ("Kusikiliza na Kuzungumza", ["Matamshi bora", "Mazungumzo"]),
                ("Kusoma", ["Ufahamu", "Msamiati"]),
                ("Kuandika", ["Insha rahisi", "Imla"]),
                ("Sarufi", ["Aina za maneno", "Sentensi"]),
            ],
            "jss": [
                ("Kusikiliza na Kuzungumza", ["Hotuba", "Mahojiano"]),
                ("Kusoma", ["Ufahamu wa kina", "Vitabu vya hadithi"]),
                ("Kuandika", ["Insha za kimaelezo", "Insha za masimulizi"]),
                ("Sarufi", ["Tungo", "Vitenzi"]),
            ],
        },
    },
    "mathematics": {
        "name": "Mathematics",
        "code": "MAT",
        "aliases": ["mathematics"],
        "groups": {
            "lower_primary": [
                ("Numbers", ["Number recognition", "Addition and subtraction", "Place value"]),
                ("Measurement", ["Length", "Mass", "Time"]),
                ("Geometry", ["Shapes", "Patterns"]),
                ("Data Handling", ["Sorting", "Pictographs"]),
            ],
            "upper_primary": [
                ("Numbers", ["Whole numbers", "Fractions", "Decimals"]),
                ("Measurement", ["Length", "Mass", "Time", "Money"]),
                ("Geometry", ["Lines and angles", "Plane figures"]),
                ("Data Handling", ["Tables and charts"]),
                ("Operations", ["Addition", "Subtraction", "Multiplication", "Division"]),
            ],
            "jss": [
                ("Numbers", ["Integers", "Rational numbers"]),
                ("Algebra", ["Algebraic expressions", "Linear equations"]),
                ("Measurement", ["Area and volume", "Time, money and ratios"]),
                ("Geometry", ["Angles", "Geometric constructions"]),
                ("Data Handling", ["Statistics", "Probability"]),
            ],
        },
    },
    "science and technology": {
        "name": "Science and Technology",
        "code": "SCI",
        "aliases": ["science and technology", "science & technology"],
        "groups": {
            "lower_primary": [
                ("Living Things", ["Plants", "Animals"]),
                ("Environment", ["Weather", "Water"]),
                ("Force and Energy", ["Force", "Light and sound"]),
                ("Digital Technology", ["Digital devices"]),
            ],
            "upper_primary": [
                ("Living Things", ["Plants", "Animals"]),
                ("Environment", ["Weather", "Water"]),
                ("Force and Energy", ["Force", "Light and sound"]),
                ("Digital Technology", ["Digital devices"]),
            ],
        },
    },
    "integrated science": {
        "name": "Integrated Science",
        "code": "INTSCI",
        "aliases": ["integrated science"],
        "groups": {
            "jss": [
                ("Living Things", ["Cell structure", "Classification"]),
                ("Mixtures, Elements and Compounds", ["Mixtures", "Acids and bases"]),
                ("Force and Energy", ["Force", "Energy transformations"]),
                ("Earth and Space", ["Atmosphere", "Hydrosphere"]),
            ],
        },
    },
    "social studies": {
        "name": "Social Studies",
        "code": "SST",
        "aliases": ["social studies"],
        "groups": {
            "lower_primary": [
                ("Natural and Built Environments", ["Home environment", "Map work"]),
                ("Citizenship", ["Rules and responsibilities"]),
                ("Culture and Heritage", ["Communities of Kenya"]),
            ],
            "upper_primary": [
                ("Natural and Built Environments", ["Map work", "Resources"]),
                ("Citizenship", ["Rights and responsibilities"]),
                ("Culture and Heritage", ["Communities of Kenya"]),
            ],
            "jss": [
                ("People and Population", ["Population distribution"]),
                ("Resources and Economic Activities", ["Agriculture", "Industries"]),
                ("Political Systems and Governance", ["Government structure"]),
            ],
        },
    },
    "cre": {
        "name": "CRE",
        "code": "CRE",
        "aliases": ["cre", "christian religious education"],
        "groups": {
            "lower_primary": [
                ("Creation", ["God the creator"]),
                ("The Bible", ["Bible stories"]),
                ("The Life of Jesus Christ", ["Jesus' teachings"]),
                ("Christian Values", ["Honesty", "Love"]),
            ],
            "upper_primary": [
                ("Creation", ["God the creator"]),
                ("The Bible", ["Bible stories"]),
                ("The Life of Jesus Christ", ["Jesus' teachings"]),
                ("Christian Values", ["Honesty", "Love"]),
            ],
            "jss": [
                ("Creation", ["Stewardship"]),
                ("The Bible", ["The Old Testament", "The New Testament"]),
                ("The Life of Jesus Christ", ["Miracles", "Parables"]),
                ("Christian Living Today", ["Christian values"]),
            ],
        },
    },
    "creative arts": {
        "name": "Creative Arts",
        "code": "CA",
        "aliases": ["creative arts"],
        "groups": {
            "lower_primary": [
                ("Visual Arts", ["Drawing", "Painting"]),
                ("Performing Arts", ["Music", "Dance"]),
            ],
            "upper_primary": [
                ("Visual Arts", ["Drawing", "Painting"]),
                ("Performing Arts", ["Music", "Dance"]),
            ],
            "jss": [
                ("Visual Arts", ["Picture making", "Graphic design"]),
                ("Performing Arts", ["Music composition", "Drama"]),
            ],
        },
    },
}


GRADE_GROUPS = {
    "lower_primary": LOWER_PRIMARY,
    "upper_primary": UPPER_PRIMARY,
    "jss": JSS,
}


def iter_entries(subject_spec):
    for group_name, strands in subject_spec["groups"].items():
        for grade_level in GRADE_GROUPS[group_name]:
            for strand_name, sub_strands in strands:
                yield grade_level, strand_name, sub_strands


def seed_expanded_strands(apps, schema_editor):
    School = apps.get_model("core", "School")
    Subject = apps.get_model("academics", "Subject")
    Strand = apps.get_model("cbc", "Strand")
    SubStrand = apps.get_model("cbc", "SubStrand")

    for school in School.objects.all():
        school_subjects = {subject.name.strip().lower(): subject for subject in Subject.objects.filter(school=school)}
        for subject_key, subject_spec in SUBJECT_CATALOG.items():
            subject = None
            for alias in subject_spec["aliases"]:
                subject = school_subjects.get(alias)
                if subject:
                    break
            if subject is None:
                try:
                    subject = Subject.objects.create(
                        school=school,
                        name=subject_spec["name"],
                        code=subject_spec["code"],
                        description="Seeded CBC core subject",
                        is_optional=False,
                        is_active=True,
                    )
                    school_subjects[subject.name.strip().lower()] = subject
                except IntegrityError:
                    print(
                        f"CBC seed hint: could not auto-create subject {subject_spec['name']} for {school.name}; "
                        "check subject code/name collisions and re-run the migration manually."
                    )
                    continue

            for order, (grade_level, strand_name, sub_strand_names) in enumerate(iter_entries(subject_spec), start=1):
                strand, _ = Strand.objects.get_or_create(
                    subject=subject,
                    grade_level=grade_level,
                    name=strand_name,
                    defaults={"order": order},
                )
                for sub_order, sub_name in enumerate(sub_strand_names, start=1):
                    SubStrand.objects.get_or_create(
                        strand=strand,
                        name=sub_name,
                        defaults={"order": sub_order},
                    )


def reverse_seed_expanded_strands(apps, schema_editor):
    Strand = apps.get_model("cbc", "Strand")
    seeded_pairs = {
        (grade_level, strand_name)
        for subject_spec in SUBJECT_CATALOG.values()
        for grade_level, strand_name, _sub_strands in iter_entries(subject_spec)
    }
    qs = Strand.objects.all()
    to_delete = [strand.pk for strand in qs if (strand.grade_level, strand.name) in seeded_pairs]
    Strand.objects.filter(pk__in=to_delete).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("cbc", "0002_seed_knec_strands"),
    ]

    operations = [
        migrations.RunPython(seed_expanded_strands, reverse_seed_expanded_strands),
    ]
