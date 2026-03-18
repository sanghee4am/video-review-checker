from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class GuidelineRule(BaseModel):
    category: str = Field(description="Rule category: 'do', 'dont', 'brand_rule', 'mandatory'")
    description: str = Field(description="Rule description")
    severity: str = Field(default="recommended", description="'strict', 'recommended', or 'optional'")


class GuidelineScene(BaseModel):
    scene_number: int = Field(description="Scene/cut number")
    time_range: Optional[str] = Field(default=None, description="Time range e.g. '0-3s'")
    description: Optional[str] = Field(default="", description="What should happen in this scene")
    visual_direction: Optional[str] = Field(default="", description="Visual/filming direction")
    script_suggestion: Optional[str] = Field(default=None, description="Suggested script/voice-over")
    text_overlay: Optional[str] = Field(default=None, description="On-screen text to include")


class ParsedGuideline(BaseModel):
    title: Optional[str] = Field(default="", description="Guideline title")
    product_name: Optional[str] = Field(default="", description="Product name")
    concept: Optional[str] = Field(default="", description="Overall concept/theme")
    content_objective: Optional[str] = Field(default="", description="Campaign objective")
    video_duration: Optional[str] = Field(default="", description="Recommended video duration")
    key_message: Optional[str] = Field(default="", description="Key message to convey")
    rules: List[GuidelineRule] = Field(default_factory=list, description="Do/Don't/Brand rules")
    scenes: List[GuidelineScene] = Field(default_factory=list, description="Scene-by-scene guide")
    mandatory_elements: List[str] = Field(default_factory=list, description="Must-include elements (hashtags, mentions, etc.)")
    recommended_flow: Optional[str] = Field(default="", description="Overall flow summary")
