from datetime import date, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from academics.models import AcademicYear, ClassSection, GradeResult, Subject, Teacher, TeachingAssignment, Term
from attendance.models import AttendanceStatus, DailyAttendance, PeriodAttendance
from core.models import School, User
from finance.models import FeeStructure, Invoice, Payment
from students.models import Enrollment, Guardian, Student, StudentGuardianRelationship


class Command(BaseCommand):
    help = "Seed deterministic Phase 2 sample data for KSMS."

    def add_arguments(self, parser):
        parser.add_argument("--school-code", default="KSMS", help="School code for the seeded school.")
        parser.add_argument(
            "--password",
            default="ChangeMe12345!",
            help="Password to apply to all seeded demo accounts.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        school_code = options["school_code"].upper()
        password = options["password"]
        today = timezone.localdate()
        school = self._create_school(school_code)
        academic_year = self._create_academic_year(school, today)
        term = self._create_term(school, academic_year, today)

        teachers = self._create_teachers(school, password)
        sections = self._create_class_sections(school, academic_year, teachers)
        subjects = self._create_subjects(school)
        self._create_teaching_assignments(school, sections, subjects, teachers)

        guardians = self._create_guardians(school, password)
        students = self._create_students(school, password)
        self._link_guardians(students, guardians)

        enrollments = self._create_enrollments(school, academic_year, term, sections, students)
        self._create_attendance(enrollments, subjects, teachers, today)

        fee_structures = self._create_fee_structures(school, academic_year, term, sections)
        self._create_invoices_and_payments(enrollments, fee_structures, teachers)
        self._create_grade_results(enrollments, subjects, teachers)

        self.stdout.write(self.style.SUCCESS("Phase 2 demo data is ready."))
        self.stdout.write("Demo accounts use the password supplied to this command.")
        self.stdout.write("Seeded users: teacher.mwangi, teacher.otieno, guardian.wanjiku, guardian.odhiambo, student.aisha, student.baraka")

    def _ensure_user(self, *, username, role, password, email, first_name, last_name, phone):
        user, _ = User.objects.get_or_create(
            username=username,
            defaults={
                "email": email,
                "first_name": first_name,
                "last_name": last_name,
                "phone": phone,
                "role": role,
                "is_active": True,
            },
        )
        changed_fields = []
        for field, value in {
            "email": email,
            "first_name": first_name,
            "last_name": last_name,
            "phone": phone,
            "role": role,
            "is_active": True,
        }.items():
            if getattr(user, field) != value:
                setattr(user, field, value)
                changed_fields.append(field)
        user.set_password(password)
        changed_fields.append("password")
        user.save()
        return user

    def _create_school(self, school_code):
        school, _ = School.objects.update_or_create(
            code=school_code,
            defaults={
                "name": "Kenya School Management System Demo School",
                "slug": f"{school_code.lower()}-demo-school",
                "registration_number": "DEMO-SCHOOL-001",
                "email": "info@ksms-demo.example.com",
                "phone": "+254712345678",
                "address": "Demo Road, Nairobi",
                "county": "Nairobi",
                "is_active": True,
            },
        )
        return school

    def _create_academic_year(self, school, today):
        start_date = date(today.year, 1, 6)
        end_date = date(today.year, 11, 20)
        academic_year, _ = AcademicYear.objects.update_or_create(
            school=school,
            name=str(today.year),
            defaults={
                "start_date": start_date,
                "end_date": end_date,
                "is_current": True,
                "notes": "Seeded Phase 2 academic year.",
            },
        )
        return academic_year

    def _create_term(self, school, academic_year, today):
        term, _ = Term.objects.update_or_create(
            academic_year=academic_year,
            name=Term.Name.TERM_2,
            defaults={
                "school": school,
                "start_date": date(today.year, 5, 4),
                "end_date": date(today.year, 8, 14),
                "is_current": True,
                "notes": "Seeded current term for Phase 2 demo data.",
            },
        )
        return term

    def _create_teachers(self, school, password):
        teacher_specs = [
            {
                "username": "teacher.mwangi",
                "email": "teacher.mwangi@ksms-demo.example.com",
                "first_name": "Grace",
                "last_name": "Mwangi",
                "phone": "+254711111111",
                "employee_number": "TCHR-001",
                "tsc_number": "TSC001",
                "specialization": "Mathematics",
            },
            {
                "username": "teacher.otieno",
                "email": "teacher.otieno@ksms-demo.example.com",
                "first_name": "Peter",
                "last_name": "Otieno",
                "phone": "+254722222222",
                "employee_number": "TCHR-002",
                "tsc_number": "TSC002",
                "specialization": "Languages",
            },
        ]
        teachers = {}
        for spec in teacher_specs:
            user = self._ensure_user(
                username=spec["username"],
                role=User.Role.TEACHER,
                password=password,
                email=spec["email"],
                first_name=spec["first_name"],
                last_name=spec["last_name"],
                phone=spec["phone"],
            )
            teacher, _ = Teacher.objects.update_or_create(
                user=user,
                defaults={
                    "school": school,
                    "employee_number": spec["employee_number"],
                    "tsc_number": spec["tsc_number"],
                    "hire_date": date(2024, 1, 8),
                    "specialization": spec["specialization"],
                },
            )
            teachers[spec["username"]] = teacher
        return teachers

    def _create_class_sections(self, school, academic_year, teachers):
        section_specs = [
            ("Form 1", "A", teachers["teacher.mwangi"], "Blue Room"),
            ("Form 1", "B", teachers["teacher.otieno"], "Green Room"),
        ]
        sections = {}
        for grade_level, stream, homeroom_teacher, room_name in section_specs:
            section, _ = ClassSection.objects.update_or_create(
                school=school,
                academic_year=academic_year,
                grade_level=grade_level,
                stream=stream,
                defaults={
                    "capacity": 40,
                    "room_name": room_name,
                    "homeroom_teacher": homeroom_teacher,
                    "notes": "Seeded Phase 2 class section.",
                },
            )
            sections[stream] = section
        return sections

    def _create_subjects(self, school):
        subject_specs = [
            ("Mathematics", "MAT", False),
            ("English", "ENG", False),
            ("Kiswahili", "KIS", False),
        ]
        subjects = {}
        for name, code, is_optional in subject_specs:
            subject, _ = Subject.objects.update_or_create(
                school=school,
                code=code,
                defaults={
                    "name": name,
                    "description": f"Seeded {name} subject.",
                    "is_optional": is_optional,
                    "is_active": True,
                },
            )
            subjects[code] = subject
        return subjects

    def _create_teaching_assignments(self, school, sections, subjects, teachers):
        assignments = [
            (sections["A"], subjects["MAT"], teachers["teacher.mwangi"]),
            (sections["A"], subjects["ENG"], teachers["teacher.otieno"]),
            (sections["A"], subjects["KIS"], teachers["teacher.otieno"]),
            (sections["B"], subjects["MAT"], teachers["teacher.mwangi"]),
            (sections["B"], subjects["ENG"], teachers["teacher.otieno"]),
            (sections["B"], subjects["KIS"], teachers["teacher.otieno"]),
        ]
        for class_section, subject, teacher in assignments:
            TeachingAssignment.objects.update_or_create(
                class_section=class_section,
                subject=subject,
                defaults={
                    "school": school,
                    "teacher": teacher,
                    "notes": "Seeded teaching assignment.",
                },
            )

    def _create_guardians(self, school, password):
        guardian_specs = [
            {
                "username": "guardian.wanjiku",
                "email": "guardian.wanjiku@ksms-demo.example.com",
                "first_name": "Jane",
                "last_name": "Wanjiku",
                "phone": "+254733333333",
                "occupation": "Business Owner",
                "national_id": "12345678",
            },
            {
                "username": "guardian.odhiambo",
                "email": "guardian.odhiambo@ksms-demo.example.com",
                "first_name": "Daniel",
                "last_name": "Odhiambo",
                "phone": "+254744444444",
                "occupation": "Civil Servant",
                "national_id": "23456789",
            },
        ]
        guardians = {}
        for spec in guardian_specs:
            user = self._ensure_user(
                username=spec["username"],
                role=User.Role.PARENT,
                password=password,
                email=spec["email"],
                first_name=spec["first_name"],
                last_name=spec["last_name"],
                phone=spec["phone"],
            )
            guardian, _ = Guardian.objects.update_or_create(
                user=user,
                defaults={
                    "school": school,
                    "occupation": spec["occupation"],
                    "national_id": spec["national_id"],
                    "postal_address": "Seeded Phase 2 guardian profile.",
                },
            )
            guardians[spec["username"]] = guardian
        return guardians

    def _create_students(self, school, password):
        student_specs = [
            {
                "username": "student.aisha",
                "email": "student.aisha@ksms-demo.example.com",
                "first_name": "Aisha",
                "last_name": "Njeri",
                "phone": "+254755555555",
                "admission_number": "ADM-001",
                "gender": Student.Gender.FEMALE,
            },
            {
                "username": "student.baraka",
                "email": "student.baraka@ksms-demo.example.com",
                "first_name": "Baraka",
                "last_name": "Otieno",
                "phone": "+254766666666",
                "admission_number": "ADM-002",
                "gender": Student.Gender.MALE,
            },
        ]
        students = {}
        for spec in student_specs:
            user = self._ensure_user(
                username=spec["username"],
                role=User.Role.STUDENT,
                password=password,
                email=spec["email"],
                first_name=spec["first_name"],
                last_name=spec["last_name"],
                phone=spec["phone"],
            )
            student, _ = Student.objects.update_or_create(
                school=school,
                admission_number=spec["admission_number"],
                defaults={
                    "user": user,
                    "gender": spec["gender"],
                    "admission_date": date(2026, 1, 8),
                    "status": Student.Status.ACTIVE,
                    "address": "Seeded Phase 2 student address.",
                },
            )
            students[spec["username"]] = student
        return students

    def _link_guardians(self, students, guardians):
        links = [
            (students["student.aisha"], guardians["guardian.wanjiku"], StudentGuardianRelationship.Relationship.MOTHER),
            (students["student.baraka"], guardians["guardian.odhiambo"], StudentGuardianRelationship.Relationship.FATHER),
        ]
        for student, guardian, relationship in links:
            StudentGuardianRelationship.objects.update_or_create(
                student=student,
                guardian=guardian,
                defaults={
                    "relationship": relationship,
                    "is_primary_contact": True,
                    "is_emergency_contact": True,
                    "is_fee_payer": True,
                    "notes": "Seeded Phase 2 guardian relationship.",
                },
            )

    def _create_enrollments(self, school, academic_year, term, sections, students):
        enrollment_specs = [
            (students["student.aisha"], sections["A"], 1),
            (students["student.baraka"], sections["B"], 2),
        ]
        enrollments = []
        for student, class_section, roll_number in enrollment_specs:
            enrollment, _ = Enrollment.objects.update_or_create(
                student=student,
                term=term,
                defaults={
                    "school": school,
                    "academic_year": academic_year,
                    "class_section": class_section,
                    "status": Enrollment.Status.ACTIVE,
                    "start_date": term.start_date,
                    "roll_number": roll_number,
                    "notes": "Seeded Phase 2 enrollment.",
                },
            )
            enrollments.append(enrollment)
        return enrollments

    def _create_attendance(self, enrollments, subjects, teachers, today):
        teacher_user = teachers["teacher.mwangi"].user
        for enrollment in enrollments:
            DailyAttendance.objects.update_or_create(
                enrollment=enrollment,
                attendance_date=today,
                defaults={
                    "status": AttendanceStatus.PRESENT,
                    "recorded_by": teacher_user,
                    "remarks": "Seeded present attendance.",
                },
            )
            DailyAttendance.objects.update_or_create(
                enrollment=enrollment,
                attendance_date=today - timedelta(days=1),
                defaults={
                    "status": AttendanceStatus.LATE,
                    "recorded_by": teacher_user,
                    "remarks": "Seeded late attendance.",
                },
            )
            PeriodAttendance.objects.update_or_create(
                enrollment=enrollment,
                attendance_date=today,
                period_number=1,
                defaults={
                    "subject": subjects["MAT"],
                    "status": AttendanceStatus.PRESENT,
                    "recorded_by": teacher_user,
                    "remarks": "Seeded period attendance.",
                },
            )

    def _create_fee_structures(self, school, academic_year, term, sections):
        fee_structures = {}
        for stream, class_section in sections.items():
            fee_structure, _ = FeeStructure.objects.update_or_create(
                school=school,
                term=term,
                class_section=class_section,
                name="Term Tuition",
                defaults={
                    "academic_year": academic_year,
                    "description": f"Seeded tuition fee for {class_section.display_name}.",
                    "amount": Decimal("15000.00"),
                    "due_date": term.start_date + timedelta(days=14),
                    "is_active": True,
                },
            )
            fee_structures[stream] = fee_structure
        return fee_structures

    def _create_invoices_and_payments(self, enrollments, fee_structures, teachers):
        first_teacher_user = teachers["teacher.mwangi"].user
        for enrollment in enrollments:
            fee_structure = fee_structures[enrollment.class_section.stream]
            invoice, _ = Invoice.objects.update_or_create(
                enrollment=enrollment,
                fee_structure=fee_structure,
                defaults={
                    "issued_date": timezone.localdate(),
                    "due_date": fee_structure.due_date,
                    "amount_due": fee_structure.amount,
                    "status": Invoice.Status.PENDING,
                    "notes": "Seeded Phase 2 invoice.",
                },
            )

            if enrollment.student.admission_number == "ADM-001":
                Payment.objects.update_or_create(
                    reference_number="PAY-MPESA-DEMO-001",
                    defaults={
                        "invoice": invoice,
                        "amount": Decimal("5000.00"),
                        "payment_method": Payment.Method.MPESA,
                        "status": Payment.Status.SUCCESSFUL,
                        "paid_at": timezone.now(),
                        "received_by": first_teacher_user,
                        "notes": "Seeded partial M-Pesa payment.",
                        "mpesa_receipt_number": "QWE123RTY",
                        "mpesa_transaction_id": "TRANS-DEMO-001",
                        "mpesa_checkout_request_id": "CHKOUT-DEMO-001",
                        "mpesa_phone_number": "+254733333333",
                        "mpesa_payer_name": "Jane Wanjiku",
                        "mpesa_result_code": 0,
                        "mpesa_result_description": "The service request is processed successfully.",
                    },
                )
            else:
                Payment.objects.update_or_create(
                    reference_number="PAY-CASH-DEMO-002",
                    defaults={
                        "invoice": invoice,
                        "amount": Decimal("15000.00"),
                        "payment_method": Payment.Method.CASH,
                        "status": Payment.Status.SUCCESSFUL,
                        "paid_at": timezone.now(),
                        "received_by": first_teacher_user,
                        "notes": "Seeded full cash payment.",
                    },
                )

    def _create_grade_results(self, enrollments, subjects, teachers):
        result_specs = {
            "ADM-001": {"MAT": Decimal("78.50"), "ENG": Decimal("81.00")},
            "ADM-002": {"MAT": Decimal("72.00"), "ENG": Decimal("76.50")},
        }
        teacher_user = teachers["teacher.mwangi"].user
        for enrollment in enrollments:
            for subject_code, score in result_specs[enrollment.student.admission_number].items():
                GradeResult.objects.update_or_create(
                    enrollment=enrollment,
                    subject=subjects[subject_code],
                    defaults={
                        "score": score,
                        "grade": "A-" if score >= Decimal("80.00") else "B",
                        "remarks": "Seeded end-term result.",
                        "recorded_by": teacher_user,
                    },
                )