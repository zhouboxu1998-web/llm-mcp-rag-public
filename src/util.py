from rich.console import Console

console = Console()


def logTitle(message: str) -> None:
    """
    在控制台中打印居中标题，两侧用白色等号填充，总长度固定为100

    Args:
        message: 要显示的标题消息
    """
    total_width = 100

    # 处理消息过长的情况
    if len(message) >= total_width - 2:
        padding = 0
        message = message[:total_width - 5] + "..."
    else:
        padding = (total_width - len(message) - 2) // 2

    # 计算左右等号的数量
    left_eq = "=" * padding
    right_eq = "=" * (total_width - len(message) - 2 - padding)

    # 使用rich打印：等号为白色，消息为黄色加粗
    console.print(f"[white]{left_eq}[/white] [bold blue]{message}[/bold blue] [white]{right_eq}[/white]")


# 测试函数
if __name__ == "__main__":
    logTitle("开始处理")
    logTitle("处理完成")
    logTitle("短标题")
    logTitle("这是一个较长的标题用于测试等号颜色")