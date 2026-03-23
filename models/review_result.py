from __future__ import annotations

import base64
import io
import re
from typing import Dict, List

from pydantic import BaseModel, Field


class SceneReview(BaseModel):
    scene_number: int
    status: str = Field(description="'pass', 'fail', or 'warning'")
    guideline_description: str = Field(default="", description="What the guideline required")
    matched_time_range: str = Field(default="", description="Matched time range in the video")
    findings: str = Field(default="", description="Detailed findings")
    suggestion: str = Field(default="", description="Revision suggestion")


class RuleReview(BaseModel):
    rule_category: str = Field(description="Rule category")
    rule_description: str = Field(description="Rule description")
    status: str = Field(description="'compliant', 'violated', or 'unclear'")
    evidence: str = Field(default="", description="Evidence (e.g. STT text quote)")
    suggestion: str = Field(default="", description="Revision suggestion if violated")


class EditingTip(BaseModel):
    scene_number: int = Field(default=0, description="Related scene number (0 = general)")
    category: str = Field(default="general", description="'font', 'effect', 'transition', 'layout', 'sfx', 'general'")
    tip: List[str] = Field(default_factory=list, description="List of specific editing tips in Korean")
    capcut_how: str = Field(default="", description="CapCut navigation path (Korean)")
    font_names: List[str] = Field(default_factory=list, description="Recommended CapCut font names")
    sfx_names: List[str] = Field(default_factory=list, description="Recommended CapCut SFX names (e.g. 'Cartoon → Scribble')")


class RevisionComparison(BaseModel):
    item: str = Field(description="Revision item description")
    status: str = Field(description="'fixed', 'still_pending', or 'partially_fixed'")
    previous_finding: str = Field(default="", description="What was found in previous review")
    current_finding: str = Field(default="", description="What is found in current review")


class ReviewReport(BaseModel):
    overall_score: int = Field(default=0, description="Score 0-100")
    overall_status: str = Field(default="pending", description="'approved', 'revision_needed', or 'rejected'")
    summary: str = Field(default="", description="Overall summary")
    scene_reviews: List[SceneReview] = Field(default_factory=list)
    rule_reviews: List[RuleReview] = Field(default_factory=list)
    mandatory_check: Dict[str, bool] = Field(default_factory=dict, description="Mandatory element check results")
    revision_items: List[str] = Field(default_factory=list, description="List of items needing revision")
    email_draft: str = Field(default="", description="Draft email for revision request in Korean")
    email_draft_en: str = Field(default="", description="Draft email for revision request in English")
    manual_review_flags: List[str] = Field(default_factory=list, description="Items that need manual human review")
    editing_tips: List[EditingTip] = Field(default_factory=list, description="CapCut editing tips for creator")
    brand_sheet_comment: str = Field(default="", description="Formatted comment for brand review sheet")
    brand_sheet_comment_en: str = Field(default="", description="Formatted comment for brand review sheet in English")
    revision_comparison: List[RevisionComparison] = Field(default_factory=list, description="Comparison with previous review")
    review_round: int = Field(default=1, description="Review round number")
    scene_thumbnails: Dict[str, str] = Field(default_factory=dict, description="Scene number → base64 JPEG thumbnail (small, ~15KB each)")

    def attach_thumbnails(self, processed_video) -> None:
        """Extract scene thumbnails from processed video and store as small base64 JPEGs.

        processed_video: ProcessedVideo with .frames (list of VideoFrame with .timestamp, .image_bytes)
        Covers both scene_reviews and editing_tips scenes.
        """
        if not processed_video or not getattr(processed_video, "frames", None):
            return

        from PIL import Image

        THUMB_MAX_W, THUMB_MAX_H = 200, 356  # Small thumbnail

        # Collect all scene_number → mid_timestamp mappings
        scene_times: Dict[int, float] = {}
        for sr in self.scene_reviews:
            m = re.search(r"([\d.]+)\s*[-~]\s*([\d.]+)", sr.matched_time_range or "")
            if m:
                scene_times[sr.scene_number] = (float(m.group(1)) + float(m.group(2))) / 2

        # Also cover editing_tips scenes that reference scene_reviews
        for tip in self.editing_tips:
            if tip.scene_number > 0 and tip.scene_number not in scene_times:
                # Try to find time from scene_reviews
                sr_match = next((sr for sr in self.scene_reviews if sr.scene_number == tip.scene_number), None)
                if sr_match:
                    m = re.search(r"([\d.]+)\s*[-~]\s*([\d.]+)", sr_match.matched_time_range or "")
                    if m:
                        scene_times[tip.scene_number] = (float(m.group(1)) + float(m.group(2))) / 2

        for scene_num, t_mid in scene_times.items():
            best_frame = min(
                processed_video.frames,
                key=lambda f: abs(f.timestamp - t_mid),
            )
            img = Image.open(io.BytesIO(best_frame.image_bytes))
            if img.mode in ("RGBA", "P", "LA"):
                img = img.convert("RGB")
            img.thumbnail((THUMB_MAX_W, THUMB_MAX_H), Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=70)
            self.scene_thumbnails[str(scene_num)] = base64.b64encode(buf.getvalue()).decode("utf-8")
