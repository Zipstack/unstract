# Usage : python manage.py shell < api/utils/seed_data/seed_data.py

from account.models import Organization, User
from project.models import Project
from prompt.models import Prompt

try:
    # Creating org
    zipOrg = Organization.objects.create(org_name="Zipstack")

    # Creating users and updating Orgs with FK
    rootUser = User.objects.create(
        org=zipOrg,
        email="johndoe@gmail.com",
        first_name="John",
        last_name="Doe",
        is_admin=True,
    )
    Organization.objects.filter(org_name__exact="Zipstack").update(
        created_by=rootUser, modified_by=rootUser
    )
    staffUser = User.objects.create(
        org=zipOrg,
        email="user1@gmail.com",
        first_name="Ron",
        last_name="Stone",
        is_admin=False,
        created_by=rootUser,
        modified_by=rootUser,
    )

    # Creating a project
    zipProject = Project.objects.create(
        org=zipOrg,
        project_name="Unstract Test",
        created_by=staffUser,
        modified_by=staffUser,
    )

    # Creating some prompts
    prompt1 = Prompt.objects.create(
        org=zipOrg,
        project=zipProject,
        version_name="v0.1.0",
        created_by=staffUser,
        modified_by=staffUser,
        prompt_input="You are a Django programmer, write a REST API \
            to support CRUD on a simple model",
    )

    prompt2 = Prompt.objects.create(
        org=zipOrg,
        project=zipProject,
        version_name="v0.1.1",
        created_by=staffUser,
        modified_by=staffUser,
        prompt_input="You are a poet (William Wordsworth), write a \
            poem on generative AI",
    )
except Exception as e:
    print("Exception while seeding data: ", e)
