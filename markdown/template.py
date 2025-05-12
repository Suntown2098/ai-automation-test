from typing import List, Dict, Any, Literal, Optional

# Dropdown -> DropdownItem
# Tab -> Input, Dropdown
class Element:
    label: str
    id: str
    description: str
    element_type: Literal["input-text", "input-password", "input-date", "button", "dropdown", "dropdown-item", "checkbox", "tab"]
    children: Optional[List["Element"]] = None # for dropdown and grid 

class Section:
    name: str
    description: str
    elements: List[Element]


class Schema:
    name: str
    description: str
    sections: List[Element]