from datetime import date, timedelta
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from telebot.types import Message
from io import BytesIO
import matplotlib.patches as patches
import colorsys
from sqlalchemy import select, func
from models.service.models import FakeChart, FakeUsersStats
from models.user.models import Seller, SellerStat, SalesReport
from models.user import SessionLocal as UserSessionLocal
from models.service import SessionLocal as ServiceSessionLocal
from datetime import date, timedelta
from sqlalchemy import func

# функция для затемнения/осветления цвета
def adjust_color_brightness(color, factor):
    r, g, b = color
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    l = max(0, min(1, l * factor))
    r, g, b = colorsys.hls_to_rgb(h, l, s)
    return (r, g, b)


def register(bot):
    @bot.message_handler(commands=['stats'])
    def stats_handler(message: Message):
        # --- Проверка FakeUsersStats ---
        service_session = ServiceSessionLocal()
        first_user = service_session.execute(
            select(FakeUsersStats).order_by(FakeUsersStats.id)
        ).scalars().first()

        # --- Получаем пользователя по telegram_id ---
        user_session = UserSessionLocal()
        try:
            seller_user = user_session.execute(
                select(Seller).where(Seller.telegram_id == str(message.from_user.id))
            ).scalars().first()

            if not seller_user:
                bot.send_message(
                    message.chat.id, 
                    "Пользователь не найден 📊\n\n"
                    "👤 Похоже, вы ещё не зарегистрированы.\n"
                    "✍️ Чтобы пользоваться статистикой, зарегистрируйтесь в системе."
                )
                return

            seller_stat = user_session.execute(
                select(SellerStat).where(SellerStat.seller_id == seller_user.id)
            ).scalars().first()

            if not seller_stat:
                bot.send_message(
                    message.chat.id, 
                    "Нет данных статистики 📊\n\n"
                    "📩 Отправьте отчёт о продажах, чтобы статистика появилась."
                )
                return
        finally:
            user_session.close()

        # --- Определяем количество фейковых пользователей и период ---
        period_days = 0
        fake_users_count = 0
        if first_user:
            period_days = first_user.period or 0
            fake_users_count = first_user.fake_users or 0

        chart_data = []
        store_names = []
        numbers = []

        if first_user and first_user.fake_active and fake_users_count >= 9:
            # --- Все пользователи из FakeChart ---
            try:
                chart_data_all = service_session.execute(
                    select(FakeChart).order_by(FakeChart.total_sold.desc())
                ).scalars().all()
            finally:
                service_session.close()

            chart_data = chart_data_all[:9]
            store_names = [f"{seller_stat.shop_name} (Вы)"] + [c.shop_name for c in chart_data]
            numbers = [seller_stat.total_sold] + [c.total_sold for c in chart_data]

        else:
            # --- Данные смешанные: реальные пользователи + фейки ---
            # Сначала определяем сколько настоящих пользователей брать
            real_users_to_take = max(0, 9 - fake_users_count)

            # Берём топ реальных пользователей по total_sold за последние period_days
            user_session = UserSessionLocal()
            try:
                # Фильтруем по дате, если period_days > 0
                if period_days > 0:
                    since_date = date.today() - timedelta(days=period_days)
                    top_seller_ids = (
                        user_session.execute(
                            select(SellerStat.seller_id, func.sum(SalesReport.sold_quantity).label("total"))
                            .join(SalesReport, SellerStat.seller_id == SalesReport.seller_id)
                            .where(SalesReport.report_date >= since_date)
                            .group_by(SellerStat.seller_id)
                            .order_by(func.sum(SalesReport.sold_quantity).desc())
                        ).all()
                    )
                else:
                    # если period_days=0, берём по всему total_sold
                    top_seller_ids = (
                        user_session.execute(
                            select(SellerStat).order_by(SellerStat.total_sold.desc())
                        ).scalars().all()
                    )
                    top_seller_ids = [(s.seller_id, s.total_sold) for s in top_seller_ids]

                # исключаем текущего пользователя
                top_seller_ids = [s for s in top_seller_ids if s[0] != seller_user.id][:real_users_to_take]

                # Получаем данные по top_seller_ids
                top_sellers_stats = []
                for s_id, total in top_seller_ids:
                    total_sold_real = total
                    stat = user_session.execute(
                        select(SellerStat).where(SellerStat.seller_id == s_id)
                    ).scalars().first()
                    if stat:
                        top_sellers_stats.append((stat.shop_name, total_sold_real))

            finally:
                user_session.close()

            # Берём нужное количество фейков
            fake_chart_data = []
            if fake_users_count > 0:
                service_session = ServiceSessionLocal()
                try:
                    chart_data_all = service_session.execute(
                        select(FakeChart).order_by(FakeChart.total_sold.desc())
                    ).scalars().all()
                    fake_chart_data = chart_data_all[:fake_users_count]
                finally:
                    service_session.close()

            # --- Формируем итоговые списки для графика ---
            store_names = [f"{seller_stat.shop_name} (Вы)"]
            numbers = [seller_stat.total_sold or 0]

            for shop_name, total in top_sellers_stats:
                store_names.append(shop_name)
                numbers.append(total)

            for f in fake_chart_data:
                store_names.append(f.shop_name)
                numbers.append(f.total_sold)

        # --- Строим DataFrame для графика ---
        df = pd.DataFrame({
            "Количество проданных пар": numbers,
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

        for day, value, base_color, num in zip(df["День"], df["Количество проданных пар"], bar_colors, df["Число"]):
            x, y, w, h = day - 0.4, 0, 0.8, value

            # основная грань
            main = patches.Polygon(
                [[x, y], [x+w, y], [x+w, y+h], [x, y+h]],
                closed=True, facecolor=base_color, linewidth=0
            )
            ax.add_patch(main)

            # боковая грань (темнее)
            side_color = adjust_color_brightness(base_color, 0.7)
            side = patches.Polygon(
                [[x+w, y], [x+w+dx, y+dy], [x+w+dx, y+dy+h], [x+w, y+h]],
                closed=True, facecolor=side_color, linewidth=0
            )
            ax.add_patch(side)

            # верхняя грань (светлее)
            top_color = adjust_color_brightness(base_color, 1.3)
            top = patches.Polygon(
                [[x, y+h], [x+w, y+h], [x+w+dx, y+h+dy], [x, y+h+dy]],
                closed=True, facecolor=top_color, linewidth=0
            )
            ax.add_patch(top)

            # подпись числа под колонкой
            ax.text(x + w/2, -max(df["Количество проданных пар"])*0.05, str(num),
                    ha="center", va="top", fontsize=10)

        # Подписи и сетка
        ax.set_xlim(0, len(df)+1)
        ax.set_ylim(-max(df["Количество проданных пар"])*0.1, max(df["Количество проданных пар"])*1.2)
        ax.set_title("Стастистика продаж по магазинам", fontsize=14, fontweight="bold")
        ax.set_xlabel("Продавцы", fontsize=12)
        ax.set_ylabel("Количество проданных пар", fontsize=12)
        ax.grid(axis="y", linestyle="--", alpha=0.5)

        # Легенда
        legend_elements = [
            plt.Line2D([0], [0], marker='s', color='w', markerfacecolor=bar_colors[i],
                       markersize=10, label=store_names[i])
            for i in range(len(df))
        ]
        ax.legend(handles=legend_elements, loc="center left", bbox_to_anchor=(1.02, 0.5))

        # Сохраняем в буфер
        buf = BytesIO()
        plt.savefig(buf, format="jpeg", dpi=150, bbox_inches="tight")
        buf.seek(0)
        plt.close()

        # --- Отправляем график ---
        bot.send_photo(
            message.chat.id, 
            buf, 
            caption=(f"👟 Общее количество проданных пар: *{seller_stat.total_sold or 0}*\n\n"
                     "💡 Ты всегда можешь контролировать свой результат и улучшать показатели!\n"
                     "📩 Не забудь вовремя отправлять отчёты о продажах, чтобы статистика оставалась актуальной."),
            parse_mode="Markdown"
        )
