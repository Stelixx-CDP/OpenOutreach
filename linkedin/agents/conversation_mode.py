from enum import Enum
from typing import Sequence

class ConversationMode(str, Enum):
    INITIAL_OUTREACH = "INITIAL_OUTREACH"   # chưa có message nào
    LEAD_REPLIED = "LEAD_REPLIED"             # message cuối cùng là từ lead → cần phản hồi + acknowledge
    NO_REPLY_BUMP = "NO_REPLY_BUMP"           # message cuối cùng là của Me, lead chưa rep → cần gentle bump

def compute_conversation_mode(messages: Sequence) -> ConversationMode:
    if not messages:
        return ConversationMode.INITIAL_OUTREACH
    last = messages[-1]
    # is_outgoing=False nghĩa là tin nhắn được nhận từ lead (incoming)
    if not last.is_outgoing:
        return ConversationMode.LEAD_REPLIED
    return ConversationMode.NO_REPLY_BUMP
