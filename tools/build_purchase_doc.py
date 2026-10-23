# -*- coding: utf-8 -*-
"""生成《项目简介与采购申请》Word 文档，供指导老师审核报销。"""
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

FONT_CN = "微软雅黑"
FONT_EN = "Calibri"


def set_font(run, size=10.5, bold=False, color=None):
    run.font.name = FONT_EN
    run.font.size = Pt(size)
    run.font.bold = bold
    if color:
        run.font.color.rgb = color
    run._element.rPr.rFonts.set(qn("w:eastAsia"), FONT_CN)


def style_doc(doc):
    normal = doc.styles["Normal"]
    normal.font.name = FONT_EN
    normal.font.size = Pt(10.5)
    normal.element.rPr.rFonts.set(qn("w:eastAsia"), FONT_CN)
    for i in range(1, 4):
        st = doc.styles[f"Heading {i}"]
        st.font.name = FONT_EN
        st.font.color.rgb = RGBColor(0x1F, 0x3A, 0x5F)
        st.element.rPr.rFonts.set(qn("w:eastAsia"), FONT_CN)


def para(doc, text="", size=10.5, bold=False, align=None, space_after=3, indent_first=False):
    p = doc.add_paragraph()
    if align is not None:
        p.alignment = align
    p.paragraph_format.space_after = Pt(space_after)
    p.paragraph_format.line_spacing = 1.22
    if indent_first:
        p.paragraph_format.first_line_indent = Cm(0.74)
    r = p.add_run(text)
    set_font(r, size, bold)
    return p


def bullet(doc, text, size=10.5):
    p = doc.add_paragraph(style="List Bullet")
    p.paragraph_format.space_after = Pt(1)
    p.paragraph_format.line_spacing = 1.2
    r = p.add_run(text)
    set_font(r, size)
    return p


def shade_cell(cell, hex_color):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_color)
    tcPr.append(shd)


def add_table(doc, headers, rows, widths=None, header_fill="1F3A5F", total_row=False):
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    if widths:
        tblPr = table._tbl.tblPr
        layout = OxmlElement("w:tblLayout")
        layout.set(qn("w:type"), "fixed")
        tblPr.append(layout)
        for i, w in enumerate(widths):
            table.columns[i].width = Cm(w)
    hdr = table.rows[0].cells
    for i, h in enumerate(headers):
        hdr[i].text = ""
        p = hdr[i].paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run(h)
        set_font(r, 9.5, bold=True, color=RGBColor(0xFF, 0xFF, 0xFF))
        shade_cell(hdr[i], header_fill)
    for ri, row in enumerate(rows):
        cells = table.add_row().cells
        for ci, val in enumerate(row):
            cells[ci].text = ""
            p = cells[ci].paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER if ci != 2 else WD_ALIGN_PARAGRAPH.LEFT
            r = p.add_run(str(val))
            set_font(r, 9.5)
        if total_row and ri == len(rows) - 1:
            for c in cells:
                shade_cell(c, "EAF0F6")
                for r in c.paragraphs[0].runs:
                    r.font.bold = True
    if widths:
        for i, w in enumerate(widths):
            for row in table.rows:
                row.cells[i].width = Cm(w)
    return table


def build(path):
    doc = Document()
    style_doc(doc)
    sec = doc.sections[0]
    sec.top_margin = Cm(2.0)
    sec.bottom_margin = Cm(2.0)
    sec.left_margin = Cm(2.2)
    sec.right_margin = Cm(2.2)

    # 标题
    t = para(doc, "项目简介与设备采购申请", size=18, bold=True,
             align=WD_ALIGN_PARAGRAPH.CENTER, space_after=2)
    para(doc, "——第十一届华为 ICT 大赛（2026-2027）中国创新赛 · 赛题1",
         size=10.5, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=10)
    para(doc, "申请日期：2026 年 10 月 23 日          申请人：参赛队（学生 3 名）          指导教师：＿＿＿＿＿",
         size=9.5, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=12)

    # 一、项目简介
    doc.add_heading("一、项目简介", level=1)
    para(doc, "项目名称：EdgeGuard —— 断网可用的用电风险识别系统", bold=True, space_after=3)
    para(doc, "参赛赛事：第十一届华为 ICT 大赛中国创新赛，赛题1“基于华为云产品打造 AI 创新应用”。"
              "初赛材料提交截止时间为 2026 年 11 月 30 日。", indent_first=True)
    para(doc, "要解决的问题：电动自行车室内充电是社区消防治理的核心痛点——电池起火后 30 秒即可充斥楼道，"
              "遇难者多为吸入电池燃烧产生的剧毒气体窒息。现有管控手段各有硬伤：", indent_first=True, space_after=3)
    bullet(doc, "电网方案：依赖智能电表的 15 分钟用电数据，没有智能电表的宿舍、出租屋、小商铺进不去；判断在主站，断网失效。")
    bullet(doc, "电气安全硬件：只能测漏电、电弧、温度等电气参数，无法识别“这是什么电器在用电”。")
    bullet(doc, "摄像头方案：存在监控盲区，涉及隐私，电池拆下带回家充电则完全失效。")
    para(doc, "我们的方案：在插座/配电回路侧采集电压、电流、功率等电参量，用轻量 AI 模型在本地完成判断"
              "（是否违规充电、是否大功率电器），并将判断结果与告警留在本地。核心特点：", indent_first=True, space_after=3)
    bullet(doc, "断网可用：判断发生在端侧，不依赖云端，断电断网仍能本地报警。")
    bullet(doc, "不依赖电网数据：无需智能电表，插上即可用，分钟级部署。")
    bullet(doc, "不涉及隐私：不采集图像，只采电参量。")
    para(doc, "当前进度：已完成技术方向论证、竞品拆解（云南电网、电气安全厂商方案）、项目代码仓库搭建"
              "（https://github.com/langqwu/edgeguard），具备采集、特征提取、模型训练与评估的完整代码框架。"
              "现阶段需采购基础采集器件，以获取四类真实负载（电瓶车充电器、电热水壶、吹风机、正常待机）的功率波形，"
              "用于训练模型并产出可量化的准确率、误报率等实验指标——这是初赛材料中“数据集”“关键代码”“量化指标”"
              "三项的必备依据。", indent_first=True)

    # 二、采购清单（另起一页，避免标题孤行）
    doc.add_page_break()
    doc.add_heading("二、采购物品清单", level=1)
    para(doc, "本次申请采购均为数据采集所需的通用电子器件与安全防护用品，不含开发板、云服务等（本期不需要）。",
         size=9.5, space_after=6)

    headers = ["序号", "物品名称", "规格/型号", "数量", "单价(元)", "小计(元)", "用途说明", "价格来源/核实方式"]
    rows = [
        ["1", "单相电能计量模块", "PZEM-004T v3.0（含开合式 CT）", "2 个", "53.00", "106.00",
         "采集电压/电流/功率；备 1 个防损坏", "阿里巴巴批发报价约 3.3–6.5 美元/个"],
        ["2", "USB 转 TTL 模块", "CH340X / CP2102", "2 个", "12.00", "24.00", "连接计量模块与电脑",
         "立创商城同类 CH340X 模块在售"],
        ["3", "带保护门插座盒", "国标 86 型明装盒", "2 个", "6.00", "12.00", "封装接线端，防触电", "京东同款约 5–8 元"],
        ["4", "带开关插排", "公牛新国标 4 位分控，3 米", "2 个", "45.90", "91.80", "承载被监测负载，便于断电",
         "京东到手价 45.9 元（2026-10 实测）"],
        ["5", "数字万用表", "得力 DL8490，入门级", "1 个", "37.15", "37.15", "接线后验电，安全必需",
         "嘉立创含税价 37.15 元"],
        ["6", "电工绝缘胶带", "PVC 阻燃，18mm", "2 卷", "6.00", "12.00", "接线绝缘", "市面常见 5–8 元/卷"],
        ["7", "铜芯导线", "1.5 mm²，5 米", "1 批", "11.05", "11.05", "内部接线", "电缆宝报价 2.21 元/米"],
        ["8", "接线端子与扎带", "UK 端子 + 尼龙扎带", "1 批", "15.00", "15.00", "接线与走线整理", "五金店常见价"],
        ["9", "备用耗材", "保险丝、备用端子", "1 批", "15.00", "15.00", "实验损耗补充", "估列"],
        ["10", "合计", "——", "——", "——", "324.00", "——", "以实际发票为准"],
    ]
    add_table(doc, headers, rows,
              widths=[0.9, 3.0, 4.0, 1.2, 1.4, 1.4, 3.6, 3.5], total_row=True)

    para(doc, "说明：以上单价于 2026 年 10 月 23 日核实，来源为电商及元器件商城公开标价（"
              "阿里巴巴 PZEM 模块批发报价、立创商城、嘉立创 FA 得力万用表含税价、京东公牛插排到手价、"
              "电缆宝铜线报价）。零售价随促销波动，最终以实际发票金额为准；"
              "如能在学校电子实验室借用万用表，相应金额可不申请。",
         size=9, space_after=8)

    # 三、可选升级项
    doc.add_heading("三、可选升级项（视初审结果与经费情况再定，本次不申请）", level=1)
    opt_headers = ["物品名称", "规格/型号", "数量", "参考单价(元)", "用途"]
    opt_rows = [
        ["端侧推理板", "树莓派 4B/5（4GB）或昇腾 Atlas 200I DK A2", "1", "400–700 / 1500+",
         "把模型部署到真实端侧，用于总决赛现场演示"],
        ["鸿蒙/星闪开发板", "如 BearPi 系列", "1", "50–300", "演示无网络条件下的本地组网告警"],
        ["温湿度传感器", "DHT22 等", "2", "15", "温度异常作为电池热失控的辅助前兆特征"],
    ]
    add_table(doc, opt_headers, opt_rows, widths=[3.2, 6.0, 1.2, 3.0, 5.6])

    # 四、经费说明
    doc.add_heading("四、经费与合规说明", level=1)
    para(doc, "1. 本次申请总额约 324 元，低于团队 1000 元预算上限，全部用于初赛阶段的数据采集与安全防护。",
         indent_first=True, space_after=3)
    para(doc, "2. 不采购开发板、GPU、云服务：初赛仅需提交材料，真实数据在普通笔记本电脑上即可采集与分析；"
              "端侧硬件与云资源待通过初赛后再申请。", indent_first=True, space_after=3)
    para(doc, "3. 220V 实验安全：全部实验将在指导教师许可的场地进行，接线前断电、接后验电，"
              "所有接线端封装于带保护门插座盒内，不在宿舍进行长时间大功率实验。", indent_first=True, space_after=3)
    para(doc, "4. 发票与报销：优先选择可开具增值税普通发票的电商自营渠道；"
              "请老师确认报销所需票据抬头、税号与提交方式，我们按学校要求执行。", indent_first=True, space_after=3)
    para(doc, "5. 物品保管：采购物品由队内指定同学登记保管，赛后归入实验室或团队资产，如实登记。",
         indent_first=True)

    # 五、审批
    doc.add_heading("五、审批意见", level=1)
    para(doc, "指导教师意见：＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿", space_after=10)
    para(doc, "签字：＿＿＿＿＿＿＿        日期：＿＿＿＿年＿＿月＿＿日", space_after=10)
    para(doc, "学院/实验室意见（如需）：＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿", space_after=10)
    para(doc, "签字：＿＿＿＿＿＿＿        日期：＿＿＿＿年＿＿月＿＿日")

    # 落款
    para(doc, "", space_after=6)
    para(doc, "申请人（学生签名）：＿＿＿＿＿＿＿  ＿＿＿＿＿＿＿  ＿＿＿＿＿＿＿",
         size=10, align=WD_ALIGN_PARAGRAPH.RIGHT)
    para(doc, "2026 年 10 月 23 日", size=10, align=WD_ALIGN_PARAGRAPH.RIGHT)

    doc.save(path)
    print(f"saved: {path}")


if __name__ == "__main__":
    import sys
    build(sys.argv[1] if len(sys.argv) > 1 else "采购申请.docx")
