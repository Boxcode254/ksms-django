from django.db import migrations


POSTGRESQL_PUBLIC_SCHEMA_HARDENING_SQL = """
DO $$
DECLARE
    role_name text;
    table_name text;
    sequence_name text;
BEGIN
    EXECUTE 'REVOKE CREATE ON SCHEMA public FROM PUBLIC';

    FOR role_name IN
        SELECT rolname
        FROM pg_roles
        WHERE rolname IN ('anon', 'authenticated')
    LOOP
        EXECUTE format('REVOKE USAGE ON SCHEMA public FROM %I', role_name);
    END LOOP;

    FOR table_name IN
        SELECT t.table_name
        FROM information_schema.tables AS t
        WHERE t.table_schema = 'public'
          AND t.table_type = 'BASE TABLE'
    LOOP
        EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', table_name);
        EXECUTE format('REVOKE ALL PRIVILEGES ON TABLE public.%I FROM PUBLIC', table_name);

        FOR role_name IN
            SELECT rolname
            FROM pg_roles
            WHERE rolname IN ('anon', 'authenticated')
        LOOP
            EXECUTE format('REVOKE ALL PRIVILEGES ON TABLE public.%I FROM %I', table_name, role_name);
        END LOOP;
    END LOOP;

    FOR sequence_name IN
        SELECT s.sequence_name
        FROM information_schema.sequences AS s
        WHERE s.sequence_schema = 'public'
    LOOP
        EXECUTE format('REVOKE ALL PRIVILEGES ON SEQUENCE public.%I FROM PUBLIC', sequence_name);

        FOR role_name IN
            SELECT rolname
            FROM pg_roles
            WHERE rolname IN ('anon', 'authenticated')
        LOOP
            EXECUTE format('REVOKE ALL PRIVILEGES ON SEQUENCE public.%I FROM %I', sequence_name, role_name);
        END LOOP;
    END LOOP;

    EXECUTE format(
        'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public REVOKE ALL ON TABLES FROM PUBLIC',
        current_user
    );
    EXECUTE format(
        'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public REVOKE ALL ON SEQUENCES FROM PUBLIC',
        current_user
    );
    EXECUTE format(
        'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public REVOKE ALL ON FUNCTIONS FROM PUBLIC',
        current_user
    );

    FOR role_name IN
        SELECT rolname
        FROM pg_roles
        WHERE rolname IN ('anon', 'authenticated')
    LOOP
        EXECUTE format(
            'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public REVOKE ALL ON TABLES FROM %I',
            current_user,
            role_name
        );
        EXECUTE format(
            'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public REVOKE ALL ON SEQUENCES FROM %I',
            current_user,
            role_name
        );
        EXECUTE format(
            'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public REVOKE ALL ON FUNCTIONS FROM %I',
            current_user,
            role_name
        );
    END LOOP;
END
$$;
"""


def harden_postgresql_public_schema(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return

    with schema_editor.connection.cursor() as cursor:
        cursor.execute(POSTGRESQL_PUBLIC_SCHEMA_HARDENING_SQL)


class Migration(migrations.Migration):

    dependencies = [
        ("admin", "0003_logentry_add_action_flag_choices"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
        ("sites", "0002_alter_domain_unique"),
        ("sessions", "0001_initial"),
        ("account", "0009_emailaddress_unique_primary_email"),
        ("students", "0002_remove_guardian_students_unique_guardian_national_id_per_school_and_more"),
        ("academics", "0004_teacher_assigned_classes_teacher_assigned_subjects_and_more"),
        ("attendance", "0001_initial"),
        ("finance", "0002_feestructure_finance_fee_school__2a8718_idx"),
        ("communication", "0001_initial"),
        ("core", "0004_user_school_and_role_scope"),
    ]

    operations = [
        migrations.RunPython(harden_postgresql_public_schema, migrations.RunPython.noop),
    ]