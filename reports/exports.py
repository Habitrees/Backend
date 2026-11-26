import csv
from io import BytesIO
from textwrap import wrap

from django.conf import settings
from django.http import HttpResponse

METRIC_KEYS = ("success_count", "failure_count", "completion_rate", "current_streak", "best_streak")


def csv_export(data):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response.write("\ufeff")
    writer = csv.writer(response)
    writer.writerow(("period", "start", "end", *METRIC_KEYS))
    for label, row in ((data["period"], data), ("previous", data["previous_period"])):
        writer.writerow((label, row["period_start"], row["period_end"], *(row.get(k, "") for k in METRIC_KEYS)))
    writer.writerow(("completion_rate_change", data["completion_rate_change"]))
    writer.writerow(("challenge_id", "title", *METRIC_KEYS))
    for row in data["challenge_performance"]:
        title = row["title"]
        if title.lstrip().startswith(("=", "+", "-", "@")) or title.startswith(("\t", "\r", "\n")):
            title = "'" + title
        writer.writerow((row["challenge_id"], title, *(row[k] for k in METRIC_KEYS)))
    return response


def pdf_export(data, rtl):
    from arabic_reshaper import reshape
    from bidi import get_display
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen.canvas import Canvas

    font_name = "HabitreeReport"
    if font_name not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(font_name, settings.REPORT_PDF_FONT))

    labels = (
        ("موفق", "ناموفق", "نرخ موفقیت", "تداوم فعلی", "بهترین تداوم") if rtl
        else ("Success", "Failure", "Completion rate", "Current streak", "Best streak")
    )

    def stats(row):
        return " | ".join(f"{label}: {row[key]}" for key, label in zip(METRIC_KEYS, labels) if key in row)

    previous = data["previous_period"]
    period_names = {"weekly": "هفتگی", "monthly": "ماهانه", "yearly": "سالانه"}
    period_name = period_names[data["period"]] if rtl else data["period"]
    report_label = "گزارش" if rtl else "Report"
    previous_label = "دوره قبل" if rtl else "Previous period"
    change_label = "تغییر نرخ موفقیت" if rtl else "Completion rate change"
    lines = [
        f"{report_label} {period_name} ({data['period_start']} / {data['period_end']})",
        stats(data),
        f"{previous_label} ({previous['period_start']} / {previous['period_end']})",
        stats(previous),
        f"{change_label}: {data['completion_rate_change']}",
    ]
    for row in data["challenge_performance"]:
        lines.extend((row["title"], stats(row)))

    output = BytesIO()
    canvas = Canvas(output, pagesize=A4)
    width, height = A4
    margin = 42
    y = height - margin
    for line in lines:
        for segment in wrap(line, width=68):
            if y < margin:
                canvas.showPage()
                y = height - margin
            text = get_display(reshape(segment), base_dir="R" if rtl else "L")
            text_width = pdfmetrics.stringWidth(text, font_name, 11)
            font_size = min(11, 11 * (width - 2 * margin) / max(text_width, 1))
            canvas.setFont(font_name, font_size)
            if rtl:
                canvas.drawRightString(width - margin, y, text)
            else:
                canvas.drawString(margin, y, text)
            y -= 17
        y -= 5
    canvas.save()
    return HttpResponse(output.getvalue(), content_type="application/pdf")
