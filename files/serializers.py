"""REST serializers for file upload input and safe metadata output."""

from rest_framework import serializers

from .models import FileRecord


class FileUploadSerializer(serializers.Serializer):
    file = serializers.FileField(required=True, allow_empty_file=False)
    description = serializers.CharField(
        required=False, allow_blank=True, allow_null=True
    )


class FileMetadataUpdateSerializer(serializers.Serializer):
    """Accept only metadata fields explicitly mutable in Phase 4."""

    description = serializers.CharField(
        required=False, allow_blank=True, allow_null=True
    )

    def validate(self, attrs):
        immutable_fields = set(self.initial_data) - {"description"}
        if immutable_fields:
            raise serializers.ValidationError(
                {
                    field: ["This field cannot be modified."]
                    for field in sorted(immutable_fields)
                }
            )
        return attrs


class FileRecordSerializer(serializers.ModelSerializer):
    file_type = serializers.ReadOnlyField()
    file_size_display = serializers.SerializerMethodField()

    class Meta:
        model = FileRecord
        fields = (
            "id",
            "filename",
            "original_filename",
            "file_size",
            "file_size_display",
            "file_type",
            "mime_type",
            "description",
            "upload_date",
        )
        read_only_fields = fields

    def get_file_size_display(self, instance: FileRecord) -> str:
        return instance.get_file_size_display()
