from rest_framework import serializers
from .models import CustomUser




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
            "info",
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
    direct_manager = ManagerSerializer()


    class Meta:
        model = CustomUser
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "is_active",
            "ldap_id",
            "use_ldap",
            "cn",
            "direct_manager",
            "department",
            "position",
            "info",
        ]
