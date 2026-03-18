from __future__ import annotations

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


class ReviewReport(BaseModel):
    overall_score: int = Field(default=0, description="Score 0-100")
    overall_status: str = Field(default="pending", description="'approved', 'revision_needed', or 'rejected'")
    summary: str = Field(default="", description="Overall summary")
    scene_reviews: List[SceneReview] = Field(default_factory=list)
    rule_reviews: List[RuleReview] = Field(default_factory=list)
    mandatory_check: Dict[str, bool] = Field(default_factory=dict, description="Mandatory element check results")
    revision_items: List[str] = Field(default_factory=list, description="List of items needing revision")
    email_draft: str = Field(default="", description="Draft email for revision request")
    manual_review_flags: List[str] = Field(default_factory=list, description="Items that need manual human review")
    editing_tips: List[EditingTip] = Field(default_factory=list, description="CapCut editing tips for creator")
