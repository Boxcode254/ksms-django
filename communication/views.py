from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import HttpResponseRedirect
from django.urls import reverse, reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from core.authz import RolePermissionRequiredMixin
from core.models import User
from core.views_mixins import HtmxTemplateMixin, SuccessMessageFormMixin, htmx_redirect

from .forms import AnnouncementFilterForm, AnnouncementForm
from .models import Announcement


# ---------------------------------------------------------------------------
# Role mixins
# ---------------------------------------------------------------------------

class AnnouncementReadMixin(RolePermissionRequiredMixin):
    """All four roles can view announcements (filtered by audience in the view)."""
    allowed_roles = (User.Role.SCHOOL_ADMIN, User.Role.TEACHER, User.Role.STUDENT, User.Role.PARENT)
    permission_required = "communication.view_announcement"


class AnnouncementWriteMixin(RolePermissionRequiredMixin):
    """Only ADMIN and TEACHER can create/edit/delete announcements."""
    allowed_roles = (User.Role.SCHOOL_ADMIN, User.Role.TEACHER)
    permission_required = "communication.add_announcement"


# ---------------------------------------------------------------------------
# Audience helpers
# ---------------------------------------------------------------------------

_AUDIENCE_FOR_ROLE = {
    User.Role.STUDENT: [Announcement.Audience.ALL, Announcement.Audience.STUDENTS],
    User.Role.PARENT: [Announcement.Audience.ALL, Announcement.Audience.PARENTS],
}


def _audience_qs_for_user(user, base_qs):
    """Restrict queryset to announcements the user's role is allowed to see."""
    allowed = _AUDIENCE_FOR_ROLE.get(user.role)
    if allowed is not None:
        return base_qs.filter(is_active=True, audience__in=allowed)
    return base_qs  # ADMIN and TEACHER see everything


# ---------------------------------------------------------------------------
# List view
# ---------------------------------------------------------------------------

class AnnouncementListView(HtmxTemplateMixin, AnnouncementReadMixin, ListView):
    model = Announcement
    template_name = "communication/announcement_list.html"
    htmx_template_name = "communication/partials/announcement_results.html"
    context_object_name = "announcements"
    paginate_by = 15

    def get_queryset(self):
        self.filter_form = AnnouncementFilterForm(self.request.GET or None, user=self.request.user)
        qs = Announcement.objects.select_related("school", "author").order_by("-created_at")

        # School-scope: users only see announcements from their own school
        user = self.request.user
        if user.is_authenticated and not user.is_superuser and user.school_id:
            qs = qs.filter(school_id=user.school_id)

        # Audience-scope for students and parents
        qs = _audience_qs_for_user(self.request.user, qs)

        if self.filter_form.is_valid():
            q = self.filter_form.cleaned_data.get("q")
            audience = self.filter_form.cleaned_data.get("audience")
            is_active = self.filter_form.cleaned_data.get("is_active")
            school = self.filter_form.cleaned_data.get("school")

            if q:
                qs = qs.filter(
                    Q(title__icontains=q) | Q(body__icontains=q) | Q(author__first_name__icontains=q)
                    | Q(author__last_name__icontains=q)
                )
            if audience:
                qs = qs.filter(audience=audience)
            if is_active:
                qs = qs.filter(is_active=(is_active == "true"))
            if school:
                qs = qs.filter(school=school)

        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["filter_form"] = self.filter_form
        context["show_audience_filter"] = "audience" in self.filter_form.fields
        context["page_title"] = "Announcements"
        context["can_create"] = self.request.user.has_perm("communication.add_announcement")
        return context


# ---------------------------------------------------------------------------
# Detail view
# ---------------------------------------------------------------------------

class AnnouncementDetailView(AnnouncementReadMixin, DetailView):
    model = Announcement
    template_name = "communication/announcement_detail.html"
    context_object_name = "announcement"

    def get_queryset(self):
        qs = Announcement.objects.select_related("school", "author")
        return _audience_qs_for_user(self.request.user, qs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        obj = self.object
        context["can_edit"] = (
            user.role == User.Role.SCHOOL_ADMIN
            or (user.role == User.Role.TEACHER and obj.author_id == user.pk)
        )
        return context


# ---------------------------------------------------------------------------
# Create view
# ---------------------------------------------------------------------------

class AnnouncementCreateView(SuccessMessageFormMixin, AnnouncementWriteMixin, CreateView):
    model = Announcement
    form_class = AnnouncementForm
    template_name = "communication/announcement_form.html"
    permission_required = "communication.add_announcement"
    success_message = "Announcement created successfully."

    def form_valid(self, form):
        form.instance.author = self.request.user
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("communication:announcement-detail", kwargs={"pk": self.object.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form_title"] = "Create announcement"
        context["submit_label"] = "Publish announcement"
        context["cancel_url"] = reverse("communication:announcement-list")
        return context


# ---------------------------------------------------------------------------
# Update view
# ---------------------------------------------------------------------------

class AnnouncementUpdateView(SuccessMessageFormMixin, AnnouncementWriteMixin, UpdateView):
    model = Announcement
    form_class = AnnouncementForm
    template_name = "communication/announcement_form.html"
    permission_required = "communication.change_announcement"
    success_message = "Announcement updated successfully."

    def dispatch(self, request, *args, **kwargs):
        # Enforce ownership for teachers before any mutation occurs.
        if request.user.role == User.Role.TEACHER:
            obj = self.get_object()
            if obj.author_id != request.user.pk:
                raise PermissionDenied("You can only edit your own announcements.")
        return super().dispatch(request, *args, **kwargs)

    def get_success_url(self):
        return reverse("communication:announcement-detail", kwargs={"pk": self.object.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form_title"] = "Edit announcement"
        context["submit_label"] = "Save changes"
        context["cancel_url"] = reverse("communication:announcement-detail", kwargs={"pk": self.object.pk})
        return context


# ---------------------------------------------------------------------------
# Delete view
# ---------------------------------------------------------------------------

class AnnouncementDeleteView(AnnouncementWriteMixin, DeleteView):
    model = Announcement
    template_name = "communication/announcement_confirm_delete.html"
    context_object_name = "announcement"
    permission_required = "communication.delete_announcement"
    success_url = reverse_lazy("communication:announcement-list")

    def dispatch(self, request, *args, **kwargs):
        # Enforce ownership for teachers before delete executes.
        if request.user.role == User.Role.TEACHER:
            obj = self.get_object()
            if obj.author_id != request.user.pk:
                raise PermissionDenied("You can only delete your own announcements.")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        messages.success(self.request, "Announcement deleted.")
        return super().form_valid(form)

