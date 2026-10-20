from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView, LogoutView, PasswordResetConfirmView
from django.shortcuts import redirect
from django.urls import reverse, reverse_lazy
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from django.utils.translation import gettext as _
from django.views.generic import FormView, ListView, TemplateView, UpdateView

from orders.models import Order
from pages import seo

from .emails import send_confirmation
from .forms import AccountSettingsForm, LoginForm, RegisterForm, ResendConfirmationForm
from .tokens import email_confirmation_token

# Remembers which address the "check your email" page should name.
CONFIRM_EMAIL_SESSION_KEY = "accounts_confirm_email"

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
    """Create a free account and email the link that confirms it.

    The student signs in once the address is confirmed; Module 1 is free
    from then on.
    """

    # template_name = "accounts/login.html"
    template_name = "pages/404.html"
    form_class = RegisterForm

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect(settings.LOGIN_REDIRECT_URL)
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        user = form.save()
        send_confirmation(user)
        self.request.session[CONFIRM_EMAIL_SESSION_KEY] = user.email
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("accounts:confirm_sent")

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


class ConfirmSentView(TemplateView):
    """ "Check your email", shown after signing up or asking for a new link."""

    template_name = "accounts/confirm_sent.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            email=self.request.session.get(CONFIRM_EMAIL_SESSION_KEY, ""),
            seo=seo.noindex(_("Check your email")),
        )
        return context


class ResendConfirmationView(FormView):
    template_name = "accounts/confirm_resend.html"
    form_class = ResendConfirmationForm
    success_url = reverse_lazy("accounts:confirm_sent")

    def form_valid(self, form):
        user = form.get_user()
        if user is not None:
            send_confirmation(user)
        self.request.session[CONFIRM_EMAIL_SESSION_KEY] = form.cleaned_data["email"]
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["seo"] = seo.noindex(_("Send a new confirmation link"))
        return context


class ConfirmEmailView(TemplateView):
    """The link in the confirmation email.

    Opening the link only shows a button; the address is confirmed and the
    student signed in on POST. Mail scanners that open every link in an
    email would otherwise use up the link (and get the session) before the
    student clicks it.
    """

    template_name = "accounts/confirm_email.html"
    user = None
    validlink = False

    def dispatch(self, request, *args, **kwargs):
        self.user = self._user_from_uid(kwargs["uidb64"])
        self.validlink = self.user is not None and email_confirmation_token.check_token(
            self.user, kwargs["token"]
        )
        return super().dispatch(request, *args, **kwargs)

    @staticmethod
    def _user_from_uid(uidb64):
        try:
            pk = force_str(urlsafe_base64_decode(uidb64))
            return get_user_model().objects.get(pk=pk)
        except (TypeError, ValueError, OverflowError, get_user_model().DoesNotExist):
            return None

    def post(self, request, *args, **kwargs):
        if not self.validlink:
            return self.get(request, *args, **kwargs)
        self.user.confirm_email()
        if not self.user.is_active:
            # Staff have blocked the account; confirming does not unblock it.
            return redirect("accounts:login")
        login(request, self.user, backend="accounts.backends.EmailBackend")
        request.session.pop(CONFIRM_EMAIL_SESSION_KEY, None)
        messages.success(
            request, _("Your email is confirmed. Module 1 is yours to study.")
        )
        return redirect("courses:dashboard")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        already = not self.validlink and self.user is not None and self.user.email_confirmed
        if self.validlink:
            title = _("Confirm your email")
        elif already:
            title = _("Your email is already confirmed")
        else:
            title = _("This link has expired")
        context.update(validlink=self.validlink, already_confirmed=already, seo=seo.noindex(title))
        return context


class StudentPasswordResetConfirmView(PasswordResetConfirmView):
    """Setting a password from an emailed link also confirms the email.

    The link could only be read in that inbox, which is all the
    confirmation link proves. Students added by staff confirm this way.
    """

    def form_valid(self, form):
        response = super().form_valid(form)
        self.user.confirm_email()
        return response


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
