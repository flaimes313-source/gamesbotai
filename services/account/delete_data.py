"""
Полное удаление данных юзера (152-ФЗ).

Удаляет ВСЁ, кроме:
- User (сам аккаунт — иначе /start создаст нового, потеряется referrer_id)
- Payment (для истории/налоговой)
- Event (для аналитики, но обнуляем user_id)

По желанию юзера, с подтверждением в UI.
"""

from sqlalchemy import delete, update

from database.connection import async_session
from database.models import (
    AIFriendMessage,
    Chat,
    Event,
    Horoscope,
    Match,
    Message,
    PhotoAnalysis,
    Profile,
    ProfileView,
    ReferralReward,
    RewardClaim,
    User,
    UserAchievement,
    UserChallenge,
    UserEngagement,
    UserNotificationSettings,
    UserQuestProgress,
    UserTest,
    UserWeeklyChallenge,
)
from utils.logging import get_logger

logger = get_logger(__name__)


async def delete_all_user_data(user_id: int) -> dict:
    """
    Удаляет все данные юзера. Возвращает счётчики удалённого.
    """
    result = {
        "profiles": 0,
        "analyses": 0,
        "tests": 0,
        "matches": 0,
        "chats": 0,
        "messages": 0,
        "ai_friend": 0,
        "achievements": 0,
        "challenges": 0,
        "weekly_challenges": 0,
        "quest_progress": 0,
        "reward_claims": 0,
        "referral_rewards": 0,
        "profile_views": 0,
        "horoscopes": 0,
        "engagement": 0,
        "notif_settings": 0,
    }

    async with async_session() as session:
        res = await session.execute(
            delete(Profile).where(Profile.user_id == user_id)
        )
        result["profiles"] = res.rowcount or 0

        res = await session.execute(
            delete(PhotoAnalysis).where(PhotoAnalysis.user_id == user_id)
        )
        result["analyses"] = res.rowcount or 0

        res = await session.execute(
            delete(UserTest).where(UserTest.user_id == user_id)
        )
        result["tests"] = res.rowcount or 0

        res = await session.execute(
            delete(Match).where(
                (Match.user1_id == user_id) | (Match.user2_id == user_id)
            )
        )
        result["matches"] = res.rowcount or 0

        res = await session.execute(
            delete(Message).where(
                (Message.sender_id == user_id) | (Message.receiver_id == user_id)
            )
        )
        result["messages"] = res.rowcount or 0

        res = await session.execute(
            delete(Chat).where(
                (Chat.user1_id == user_id) | (Chat.user2_id == user_id)
            )
        )
        result["chats"] = res.rowcount or 0

        res = await session.execute(
            delete(AIFriendMessage).where(AIFriendMessage.user_id == user_id)
        )
        result["ai_friend"] = res.rowcount or 0

        res = await session.execute(
            delete(UserAchievement).where(UserAchievement.user_id == user_id)
        )
        result["achievements"] = res.rowcount or 0

        res = await session.execute(
            delete(UserChallenge).where(UserChallenge.user_id == user_id)
        )
        result["challenges"] = res.rowcount or 0

        res = await session.execute(
            delete(UserWeeklyChallenge).where(UserWeeklyChallenge.user_id == user_id)
        )
        result["weekly_challenges"] = res.rowcount or 0

        res = await session.execute(
            delete(UserQuestProgress).where(UserQuestProgress.user_id == user_id)
        )
        result["quest_progress"] = res.rowcount or 0

        res = await session.execute(
            delete(RewardClaim).where(RewardClaim.user_id == user_id)
        )
        result["reward_claims"] = res.rowcount or 0

        res = await session.execute(
            delete(ReferralReward).where(
                (ReferralReward.referrer_id == user_id)
                | (ReferralReward.referred_id == user_id)
            )
        )
        result["referral_rewards"] = res.rowcount or 0

        res = await session.execute(
            delete(ProfileView).where(
                (ProfileView.viewer_id == user_id)
                | (ProfileView.viewed_id == user_id)
            )
        )
        result["profile_views"] = res.rowcount or 0

        res = await session.execute(
            delete(Horoscope).where(Horoscope.user_id == user_id)
        )
        result["horoscopes"] = res.rowcount or 0

        res = await session.execute(
            delete(UserEngagement).where(UserEngagement.user_id == user_id)
        )
        result["engagement"] = res.rowcount or 0

        res = await session.execute(
            delete(UserNotificationSettings).where(
                UserNotificationSettings.user_id == user_id
            )
        )
        result["notif_settings"] = res.rowcount or 0

        # Event: обнуляем user_id, но не удаляем (для аналитики)
        await session.execute(
            update(Event)
            .where(Event.user_id == user_id)
            .values(user_id=None)
        )

        # User: обнуляем premium_until (но НЕ удаляем)
        await session.execute(
            update(User)
            .where(User.id == user_id)
            .values(premium_until=None)
        )

        await session.commit()

    logger.info(
        f"[DELETE_DATA] user_id={user_id} deleted: "
        f"profiles={result['profiles']}, analyses={result['analyses']}, "
        f"messages={result['messages']}, ai_friend={result['ai_friend']}"
    )
    return result