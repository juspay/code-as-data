from typing import Optional, List, Dict
from pydantic import BaseModel


class StateDependencies(BaseModel):
    db: Optional[List[str]]
    env: Optional[List[str]]                          
    redis: Optional[List[str]]                      

class MetaData(BaseModel):
    function_name: str
    behavior_summary: str
    preconditions: List[str]
    postconditions: List[str]
    state_dependencies: Optional[StateDependencies]
    side_effects: List[str]

class ChildCallRelation(BaseModel):
    child: str
    condition: str

class DetailedMetaData(BaseModel):
    function_name: str
    behavior_summary: str
    preconditions: List[str]
    postconditions: List[str]
    state_dependencies: Optional[StateDependencies]
    side_effects: List[str]
    child_call_relationship: List[ChildCallRelation]