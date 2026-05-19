from django.db import migrations, models
import django.db.models.deletion


def forward_user_school_and_roles(apps, schema_editor):
    User = apps.get_model("core", "User")
    Teacher = apps.get_model("academics", "Teacher")
    Student = apps.get_model("students", "Student")
    Guardian = apps.get_model("students", "Guardian")

    teacher_school = dict(Teacher.objects.values_list("user_id", "school_id"))
    student_school = dict(Student.objects.values_list("user_id", "school_id"))
    guardian_school = dict(Guardian.objects.values_list("user_id", "school_id"))

    for user in User.objects.all().only("id", "role", "is_superuser", "school_id"):
        if user.is_superuser:
            user.role = "superuser"
            user.school_id = None
            user.save(update_fields=["role", "school"])
            continue

        if user.role == "admin":
            user.role = "school_admin"

        if user.school_id is None:
            school_id = (
                teacher_school.get(user.id)
                or student_school.get(user.id)
                or guardian_school.get(user.id)
            )
            if school_id:
                user.school_id = school_id
                user.save(update_fields=["role", "school"])
                continue

        # If no linked profile school exists, still persist role migration.
        user.save(update_fields=["role"])


def noop_reverse(apps, schema_editor):
    # Intentionally no-op to avoid destructive role/school rollback.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0001_initial"),
        ("students", "0002_remove_guardian_students_unique_guardian_national_id_per_school_and_more"),
        ("core", "0003_alter_user_avatar_alter_user_phone_school"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="school",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="users",
                to="core.school",
            ),
        ),
        migrations.AlterField(
            model_name="user",
            name="role",
            field=models.CharField(
                choices=[
                    ("superuser", "Superuser"),
                    ("school_admin", "School Admin"),
                    ("teacher", "Teacher"),
                    ("student", "Student"),
                    ("parent", "Parent"),
                ],
                db_index=True,
                default="parent",
                max_length=20,
            ),
        ),
        migrations.RunPython(forward_user_school_and_roles, noop_reverse),
    ]
