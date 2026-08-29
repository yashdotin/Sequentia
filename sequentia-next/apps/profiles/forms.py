from django import forms

from .models import LearnerProfile


class OnboardingForm(forms.Form):
    destination_role = forms.CharField(
        label="Target role", max_length=200, required=False
    )
    known_skills = forms.CharField(
        label="Known skills", required=False, widget=forms.HiddenInput
    )
    interests = forms.CharField(
        label="Interests", required=False, widget=forms.HiddenInput
    )
    experience_level = forms.ChoiceField(
        label="Overall experience level",
        choices=LearnerProfile.EXPERIENCE_CHOICES,
        initial="beginner",
    )
    extra_context = forms.CharField(
        label="Anything else Sequentia should know",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("destination_role") and not cleaned.get("extra_context"):
            raise forms.ValidationError(
                "Tell Sequentia what you're aiming for — pick a role or add a note."
            )
        return cleaned


class ProfileEditForm(forms.ModelForm):
    class Meta:
        model = LearnerProfile
        fields = ["goal_text", "target_role", "experience_level"]
        widgets = {
            "goal_text": forms.Textarea(attrs={"rows": 3}),
        }
