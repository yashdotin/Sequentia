from django import forms

PATH_FEEDBACK_CHOICES = [
    ("more_projects", "More projects"),
    ("less_theory", "Less theory"),
    ("faster_path", "Faster path"),
    ("slower_path", "Slower path"),
    ("focus_ai", "Focus on AI"),
    ("focus_data_science", "Focus on data science"),
    ("focus_cloud", "Focus on cloud"),
    ("other", "Other"),
]


class PathFeedbackForm(forms.Form):
    changes = forms.MultipleChoiceField(
        choices=PATH_FEEDBACK_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        required=True,
    )
