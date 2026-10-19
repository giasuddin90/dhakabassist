from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView, LogoutView
from django.urls import reverse, reverse_lazy
from django.utils.translation import gettext as _
from django.views.generic import FormView, ListView, UpdateView

from orders.models import Order
from pages import seo

from .forms import AccountSettingsForm, LoginForm, RegisterForm

SESSION_UNTIL_CLOSE = 0


class StudentLoginView(LoginView):
    template_name = "accounts/login.html"
    form_class = LoginForm
    redirect_authenticated_user = True

    def form_valid(self, form):
        response = super().form_valid(form)
        if not form.cleaned_data.get("remember_me"):
            self.request.session.set_expiry(SESSION_UNTIL_CLOSE)
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            mode="login",
            seo=seo.SEO(
                title=_("Log in"),
                description=_("Sign in to continue your music theory course."),
                canonical_path=reverse("accounts:login"),
                robots="noindex, follow",
            ),
        )
        return context


class RegisterView(FormView):
    """Create a free account. Module 1 becomes available immediately."""

    template_name = "accounts/login.html"
    form_class = RegisterForm

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            from django.shortcuts import redirect

            return redirect(settings.LOGIN_REDIRECT_URL)
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        user = form.save()
        login(self.request, user, backend="accounts.backends.EmailBackend")
        messages.success(
            self.request, _("Your account is ready. Module 1 is yours to study.")
        )
        return super().form_valid(form)

    def get_success_url(self):
        return self.request.POST.get("next") or reverse("courses:dashboard")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            mode="register",
            seo=seo.SEO(
                title=_("Create your account"),
                description=_(
                    "Create a free DhakaBassist account and study Module 1 of "
                    "Foundations of Music at no cost."
                ),
                canonical_path=reverse("accounts:register"),
                robots="noindex, follow",
            ),
        )
        return context


class StudentLogoutView(LogoutView):
    next_page = reverse_lazy("pages:home")


class AccountSettingsView(LoginRequiredMixin, UpdateView):
    template_name = "accounts/settings.html"
    form_class = AccountSettingsForm
    success_url = reverse_lazy("accounts:settings")

    def get_object(self, queryset=None):
        return self.request.user

    def form_valid(self, form):
        messages.success(self.request, _("Your account details have been saved."))
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["seo"] = seo.noindex(
            _("Account settings"), canonical_path=reverse("accounts:settings")
        )
        return context


class OrderHistoryView(LoginRequiredMixin, ListView):
    template_name = "accounts/orders.html"
    context_object_name = "orders"

    def get_queryset(self):
        return Order.objects.filter(student=self.request.user).select_related("course")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["seo"] = seo.noindex(
            _("Order history"), canonical_path=reverse("accounts:orders")
        )
        return context
