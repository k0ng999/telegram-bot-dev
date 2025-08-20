import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from telebot.types import Message
from io import BytesIO
import matplotlib.patches as patches
import colorsys
from sqlalchemy import select
from models.service.models import FakeChart, fake_users_stats
from models.service import SessionLocal as ServiceSessionLocal
from models.user.models import SellerStat
from models.user import SessionLocal as UserSessionLocal

def adjust_color_brightness(color, factor):
    r, g, b = color
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    l = max(0, min(1, l * factor))
    r, g, b = colorsys.hls_to_rgb(h, l, s)
    return (r, g, b)

def register(bot):
    @bot.message_handler(commands=['stats'])
    def stats_handler(message: Message):
        # --- Проверяем fake_users_stats ---
        service_session = ServiceSessionLocal()
        user_session = UserSessionLocal()
        try:
            first_user = service_session.execute(
                select(fake_users_stats).order_by(fake_users_stats.id)
            ).scalars().first()

            if not (first_user and first_user.fake_active):
                bot.send_message(message.chat.id, "Нет данных для отображения 📊")
                return

            # Получаем пользователя по Telegram ID
            seller = user_session.execute(
                select(SellerStat).where(SellerStat.seller_id == message.from_user.id)
            ).scalars().first()

            if not seller:
                bot.send_message(message.chat.id, "Нет данных пользователя 📊")
                return

            # Берём 9 записей из FakeChart, сортируем по total_bonus по возрастанию
            chart_data = service_session.execute(
                select(FakeChart).order_by(FakeChart.total_bonus).limit(9)
            ).scalars().all()

        finally:
            service_session.close()
            user_session.close()

        # --- Формируем данные для графика ---
        numbers = [seller.total_bonus] + [c.total_bonus for c in chart_data]
        store_names = [seller.shop_name] + [c.name for c in chart_data]

        df = pd.DataFrame({
            "Продажи": numbers,
            "Магазин": store_names,
            "Число": numbers
        })
        df["День"] = range(1, len(df) + 1)

        # Цвета (tab10)
        colors = plt.cm.tab10.colors
        bar_colors = [colors[i % len(colors)] for i in range(len(df))]

        # --- Построение графика ---
        fig, ax = plt.subplots(figsize=(9, 6))
        dx, dy = 0.2, 0.2

        for day, value, base_color, num in zip(df["День"], df["Продажи"], bar_colors, df["Число"]):
            x, y, w, h = day - 0.4, 0, 0.8, value

            main = patches.Polygon(
                [[x, y], [x+w, y], [x+w, y+h], [x, y+h]],
                closed=True, facecolor=base_color, linewidth=0
            )
            ax.add_patch(main)

            side_color = adjust_color_brightness(base_color, 0.7)
            side = patches.Polygon(
                [[x+w, y], [x+w+dx, y+dy], [x+w+dx, y+dy+h], [x+w, y+h]],
                closed=True, facecolor=side_color, linewidth=0
            )
            ax.add_patch(side)

            top_color = adjust_color_brightness(base_color, 1.3)
            top = patches.Polygon(
                [[x, y+h], [x+w, y+h], [x+w+dx, y+h+dy], [x, y+h+dy]],
                closed=True, facecolor=top_color, linewidth=0
            )
            ax.add_patch(top)

            ax.text(x + w/2, -max(df["Продажи"])*0.05, str(num),
                    ha="center", va="top", fontsize=10)

        ax.set_xlim(0, len(df)+1)
        ax.set_ylim(-max(df["Продажи"])*0.1, max(df["Продажи"])*1.2)
        ax.set_title("График продаж по магазинам", fontsize=14, fontweight="bold")
        ax.set_xlabel("Дни", fontsize=12)
        ax.set_ylabel("Продажи", fontsize=12)
        ax.grid(axis="y", linestyle="--", alpha=0.5)

        legend_elements = [
            plt.Line2D([0], [0], marker='s', color='w', markerfacecolor=bar_colors[i],
                       markersize=10, label=store_names[i])
            for i in range(len(df))
        ]
        ax.legend(handles=legend_elements, loc="center left", bbox_to_anchor=(1.02, 0.5))

        buf = BytesIO()
        plt.savefig(buf, format="jpeg", dpi=150, bbox_inches="tight")
        buf.seek(0)
        plt.close()

        bot.send_photo(message.chat.id, buf, caption="Ваш график продаж 📊 (с номерами под колонками)")
