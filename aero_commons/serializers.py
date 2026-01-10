from rest_framework import serializers
from .models import CustomUser, Department, Position


class ManagerSerializer(serializers.ModelSerializer):
    """
    Serializer for the UserInfo model.
    """

    class Meta:
        model = CustomUser
        fields = (
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
        )


class CustomUserSerializer(serializers.ModelSerializer):
    """
    Main User Serializer.
    Combines Position (with Department) and UserInfo.
    """

    position = serializers.CharField(source="position.title_en", read_only=True)
    department = serializers.CharField(
        source="position.department.name", read_only=True
    )
    direct_manager = ManagerSerializer(read_only=True)

    class Meta:
        model = CustomUser
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "is_active",
            "is_staff",
            "ldap_id",
            # Organization Info
            "cn",
            "direct_manager",
            "department",
            "position",
            # Personal Info
            "thumbnail",
            "identify_code",
            "last_degree",
            "address",
            "phone",
            "birth_date",
            "personnel_code",
        ]
        read_only_fields = [
            "cn",
            "email",
            "phone",
            "username",
            "thumbnail",
            "personnel_code",
        ]


class DepartmentSerializer(serializers.ModelSerializer):

    class Meta:
        model = Department
        fields = "__all__"


class PositionSerializer(serializers.ModelSerializer):

    class Meta:
        model = Position
        fields = "__all__"
