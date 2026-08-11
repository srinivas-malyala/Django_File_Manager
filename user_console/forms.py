"""Forms for the basic server-rendered file console."""

from django import forms

from files.validators import FileValidator
from files.batch import BatchFileService
from files.models import FileRecord


class BoundedModelMultipleChoiceField(forms.ModelMultipleChoiceField):
    """Reject oversized ID collections before issuing an ownership query."""

    def clean(self, value):
        if value and len(value) > BatchFileService.MAX_BATCH_FILES:
            raise forms.ValidationError(
                f"Select no more than {BatchFileService.MAX_BATCH_FILES} files."
            )
        return super().clean(value)


class ConsoleFileUploadForm(forms.Form):
    """Collect file content and optional metadata for the shared upload service."""

    file = forms.FileField(
        widget=forms.ClearableFileInput(
            attrs={
                "class": "form-control",
                "accept": (
                    ".jpg,.jpeg,.png,.gif,.bmp,.pdf,.doc,.docx,.txt,.rtf,"
                    ".xls,.xlsx,.csv,.zip,.rar,.7z"
                ),
            }
        )
    )
    description = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 4,
                "placeholder": "Optional description",
            }
        ),
    )


class ConsoleFileSearchForm(forms.Form):
    """Render the validated Phase 5 query contract for browser users."""

    file_type_choices = [("", "All file types")] + [
        (extension, extension.upper())
        for extension in sorted(FileValidator.ALLOWED_EXTENSIONS)
    ]
    sort_choices = [
        ("-upload_date", "Newest first"),
        ("upload_date", "Oldest first"),
        ("name", "Name A-Z"),
        ("-name", "Name Z-A"),
        ("file_size", "Smallest first"),
        ("-file_size", "Largest first"),
        ("file_type", "File type A-Z"),
        ("-file_type", "File type Z-A"),
    ]

    search = forms.CharField(
        required=False,
        max_length=200,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "Name or description"}
        ),
    )
    file_type = forms.ChoiceField(
        required=False,
        choices=file_type_choices,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    mime_type = forms.CharField(
        required=False,
        max_length=100,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "e.g. application/pdf"}
        ),
    )
    date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}),
    )
    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}),
    )
    min_size = forms.IntegerField(
        required=False,
        min_value=0,
        label="Minimum size (bytes)",
        widget=forms.NumberInput(attrs={"class": "form-control", "min": 0}),
    )
    max_size = forms.IntegerField(
        required=False,
        min_value=0,
        label="Maximum size (bytes)",
        widget=forms.NumberInput(attrs={"class": "form-control", "min": 0}),
    )
    sort = forms.ChoiceField(
        required=False,
        choices=sort_choices,
        initial="-upload_date",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    page_size = forms.ChoiceField(
        required=False,
        choices=(("20", "20"), ("50", "50"), ("100", "100")),
        initial="20",
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    def clean(self):
        cleaned_data = super().clean()
        date_from = cleaned_data.get("date_from")
        date_to = cleaned_data.get("date_to")
        if date_from and date_to and date_from > date_to:
            self.add_error("date_to", "End date must be on or after start date.")
        min_size = cleaned_data.get("min_size")
        max_size = cleaned_data.get("max_size")
        if min_size is not None and max_size is not None and min_size > max_size:
            self.add_error("max_size", "Maximum size must be at least minimum size.")
        return cleaned_data


class BatchFileOperationForm(forms.Form):
    action = forms.ChoiceField(choices=(("delete", "Delete"), ("download", "Download")))
    file_ids = BoundedModelMultipleChoiceField(
        queryset=FileRecord.objects.none(),
        required=True,
    )

    def __init__(self, *args, user, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields["file_ids"].queryset = FileRecord.objects.filter(uploaded_by=user)
