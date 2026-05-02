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
            "first_name_fa",
            "last_name",
            "last_name_fa",
        )


from rest_framework import serializers


class CustomUserSerializer(serializers.ModelSerializer):
    """
    Main User Serializer.
    Combines Position (with Department) and UserInfo.
    """

    position = serializers.CharField(source="position.title_en", read_only=True)
    department = serializers.CharField(
        source="position.department.name", read_only=True
    )

    groups = serializers.SerializerMethodField()
    permissions = serializers.SerializerMethodField()

    direct_manager = ManagerSerializer(read_only=True)

    def __init__(self, *args, **kwargs):
        # Initialize the superclass
        super().__init__(*args, **kwargs)

        # Get the request object from the context
        request = self.context.get("request")

        # Check if the request exists and has query_params
        if request and hasattr(request, "query_params"):
            # Check the value of 'include_permission' query parameter
            include_permission = (
                request.query_params.get("include_permission", "false").lower()
                == "true"
            )

            # Remove the 'permissions' field if include_permission is not True
            if not include_permission:
                self.fields.pop("permissions", None)

    class Meta:
        model = CustomUser
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "first_name_fa",
            "last_name",
            "last_name_fa",
            "is_active",
            "is_staff",
            "ldap_id",
            "groups",
            "permissions",
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
            "is_active",
            "is_staff",
            "thumbnail",
            "ldap_id",
            "personnel_code",
        ]

    def get_groups(self, obj):
        # Returns a list of group names, e.g., ['Admin', 'Editors']
        return list(obj.groups.values_list("name", flat=True))

    def get_permissions(self, obj):
        # Returns standard Django permissions, e.g., ['auth.add_user', 'app.change_model']
        return list(obj.get_all_permissions())


class UserBriefSerializer(serializers.ModelSerializer):

    class Meta:
        model = CustomUser
        fields = [
            "id",
            "email",
            "username",
            "first_name",
            "first_name_fa",
            "last_name",
            "last_name_fa",
            "position",
            "personnel_code",
        ]


class DepartmentSerializer(serializers.ModelSerializer):

    class Meta:
        model = Department
        fields = "__all__"


class PositionSerializer(serializers.ModelSerializer):

    department_detail = DepartmentSerializer(source="department", read_only=True)

    class Meta:
        model = Position
        fields = [
            "id",
            "title_en",
            "title_fa",
            "hidden",
            "department",
            "department_detail",
        ]
        extra_kwargs = {"department": {"write_only": True}}
