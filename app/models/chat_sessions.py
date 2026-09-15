"""Chat session model module.

This module defines the ChatSession model for storing chat conversation sessions
between users and the AI assistant.
"""

from tortoise import fields, models


class ChatSession(models.Model):
    """Chat session model for storing conversation sessions.

    Attributes:
        id: Primary key UUID.
        account: Foreign key to Account model.
        profile: Foreign key to Profile model.
        title: Optional session title.
        created_at: Session creation timestamp.
        updated_at: Last update timestamp.
    """

    id = fields.UUIDField(pk=True)
    account = fields.ForeignKeyField("models.Account", related_name="chat_sessions")
    profile = fields.ForeignKeyField("models.Profile", related_name="chat_sessions")
    title = fields.CharField(max_length=64, null=True)
    # 옵션 D — N turn 마다 SessionCompactService 가 비동기 갱신.
    # 다음 turn 의 Router LLM history 앞에 system message 로 prepend 되어 컨텍스트 압축 효과.
    summary = fields.TextField(null=True, description="Compact medical-context summary (옵션 D)")
    summary_updated_at = fields.DatetimeField(null=True, description="Last successful compact run timestamp")
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "chat_sessions"
        indexes = [
            ("account_id", "created_at"),
            ("profile_id",),
        ]
