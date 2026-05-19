from django.contrib import admin

from cbc.models import (
    CBCAssessment,
    CBCCoreCompetency,
    CBCReport,
    Strand,
    SubStrand,
)


class SubStrandInline(admin.TabularInline):
    model = SubStrand
    extra = 0


@admin.register(Strand)
class StrandAdmin(admin.ModelAdmin):
    list_display = ("subject", "grade_level", "name", "code", "order")
    list_filter = ("subject", "grade_level")
    search_fields = ("name", "code", "subject__name")
    inlines = [SubStrandInline]


@admin.register(SubStrand)
class SubStrandAdmin(admin.ModelAdmin):
    list_display = ("strand", "name", "code", "order")
    list_filter = ("strand__subject", "strand__grade_level")
    search_fields = ("name", "strand__name")


class CBCAssessmentInline(admin.TabularInline):
    model = CBCAssessment
    extra = 0
    readonly_fields = ("level",)


class CBCCoreCompetencyInline(admin.TabularInline):
    model = CBCCoreCompetency
    extra = 0


@admin.register(CBCReport)
class CBCReportAdmin(admin.ModelAdmin):
    list_display = (
        "enrollment",
        "term",
        "average_score",
        "overall_level",
        "published_at",
    )
    list_filter = ("term", "published_at")
    search_fields = (
        "enrollment__student__admission_number",
        "enrollment__student__user__first_name",
        "enrollment__student__user__last_name",
    )
    inlines = [CBCAssessmentInline, CBCCoreCompetencyInline]


@admin.register(CBCAssessment)
class CBCAssessmentAdmin(admin.ModelAdmin):
    list_display = ("report", "subject", "strand", "sub_strand", "score", "level")
    list_filter = ("subject", "level")
    search_fields = ("report__enrollment__student__admission_number",)
    readonly_fields = ("level",)


@admin.register(CBCCoreCompetency)
class CBCCoreCompetencyAdmin(admin.ModelAdmin):
    list_display = ("report", "competency", "level")
    list_filter = ("competency", "level")
