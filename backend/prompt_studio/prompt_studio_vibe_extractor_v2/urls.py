from rest_framework.routers import SimpleRouter

from prompt_studio.prompt_studio_vibe_extractor_v2.views import (
    VibeExtractorProjectView,
)

router = SimpleRouter()
router.register(
    r"vibe-extractor",
    VibeExtractorProjectView,
    basename="vibe-extractor",
)

urlpatterns = router.urls
