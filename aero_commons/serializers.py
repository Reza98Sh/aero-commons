from rest_framework import serializers
from django.db.models import  Exists, OuterRef


from .models import  Department, Position
from django.contrib.auth import get_user_model

User = get_user_model()

class ManagerSerializer(serializers.ModelSerializer):
    """
    Serializer for the UserInfo model.
    """

    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "email",
            "first_name",
            "first_name_fa",
            "last_name",
            "last_name_fa",
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

    groups = serializers.SerializerMethodField()
    is_manager = serializers.BooleanField(read_only=True)

    direct_manager = ManagerSerializer(read_only=True)



    class Meta:
        model = User
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
            "is_manager",
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
            "is_manager",
            "ldap_id",
            "personnel_code",
        ]

    def get_groups(self, obj):
        # Returns a list of group names, e.g., ['Admin', 'Editors']
        return list(obj.groups.values_list("name", flat=True))



    @staticmethod
    def annotate_queryset(queryset):
        
        queryset = queryset.select_related(
            "position",  # Position of current user
            "position__department",  # Department of current user's position
            "direct_manager",  # Direct manager (self-referential)
            "direct_manager__position",  # Position of direct manager
            "direct_manager__position__department",  # Department of direct manager's position
        ).all()
        
        # Annotate is_manager as True if the user has any subordinates
        subordinates = User.objects.filter(direct_manager=OuterRef("pk"))
        queryset = queryset.annotate(is_manager=Exists(subordinates))
        
        
        return queryset


class UserBriefSerializer(serializers.ModelSerializer):

    class Meta:
        model = User
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
