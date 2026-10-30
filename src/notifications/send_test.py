from src.notifications.sender import send_notification_to_user

if __name__ == "__main__":
    user_id = 5

    sent_count = send_notification_to_user(
        user_id=user_id,
        title="Tin mới",
        body="Bạn có bài báo mới phù hợp với sở thích.",
    )

    print(f"Firebase đã chấp nhận gửi đến {sent_count} thiết bị")
