"""Render an engine result into the pre-EOFY PDF report."""
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_RIGHT

INK = colors.HexColor("#1c2230"); SLATE = colors.HexColor("#5b6472"); LINE = colors.HexColor("#e2e5ea")
ORE = colors.HexColor("#c2571f"); ORE_BG = colors.HexColor("#faece7")
GREEN = colors.HexColor("#0f6e56"); GREEN_BG = colors.HexColor("#e1f5ee")
RED = colors.HexColor("#a32d2d"); BLUE = colors.HexColor("#185fa5"); BLUE_BG = colors.HexColor("#e6f1fb")
PANEL = colors.HexColor("#f6f7f9")
_ss = getSampleStyleSheet()

def _s(name, **kw):
    return ParagraphStyle(name, parent=kw.pop("parent", _ss["Normal"]), **kw)

body = _s("body", fontName="Helvetica", fontSize=9, leading=13, textColor=INK)
small = _s("small", fontName="Helvetica", fontSize=7.5, leading=10, textColor=SLATE)
cell = _s("cell", fontName="Helvetica", fontSize=8, leading=11, textColor=INK)
cellr = _s("cellr", parent=cell, alignment=TA_RIGHT)
cellb = _s("cellb", fontName="Helvetica-Bold", fontSize=8, leading=11, textColor=INK)
cellbr = _s("cellbr", parent=cellb, alignment=TA_RIGHT)
hd = _s("hd", fontName="Helvetica-Bold", fontSize=7.5, leading=10, textColor=colors.white)
hdr = _s("hdr", parent=hd, alignment=TA_RIGHT)

def money(x, dp=0):
    return ("-$%s" % f"{abs(x):,.{dp}f}") if x < 0 else ("$%s" % f"{x:,.{dp}f}")

def build(result, path):
    a, cgt, income, tax, xray, actions = (result["account"], result["cgt"], result["income"],
                                          result["tax"], result["xray"], result["actions"])
    made = cgt["gains_after_losses"] + income["au_cash"] + income["foreign_cash"]
    save = sum(x["saving"] for x in actions)
    after = tax["net_tax"] - save
    story = []

    logo = Table([[Paragraph("◆", _s("lg", fontName="Helvetica-Bold", fontSize=15, textColor=ORE)),
                   Paragraph("HoldCapital", _s("wm", fontName="Helvetica-Bold", fontSize=15, textColor=INK))]],
                 colWidths=[7*mm, 40*mm])
    logo.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"MIDDLE"),("LEFTPADDING",(0,0),(-1,-1),0),
                              ("TOPPADDING",(0,0),(-1,-1),0),("BOTTOMPADDING",(0,0),(-1,-1),0)]))
    hb = Table([[logo, Paragraph(f"Pre-EOFY tax position<br/>Generated {a.today:%d %B %Y}",
                                 _s("hr", parent=small, alignment=TA_RIGHT))]], colWidths=[100*mm, 74*mm])
    hb.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"MIDDLE"),("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),0)]))
    story += [hb, Spacer(1,4), HRFlowable(width="100%", thickness=1, color=INK), Spacer(1,10)]

    story.append(Paragraph(f"FY {a.fy_start:%Y}–{a.fy_end:%y} capital gains & income summary",
                           _s("h1", fontName="Helvetica-Bold", fontSize=20, textColor=INK, leading=23)))
    story.append(Spacer(1,2))
    story.append(Paragraph(f"{result.get('portfolio_label','All portfolios')} &nbsp;·&nbsp; {a.entity.title()} taxpayer &nbsp;·&nbsp; "
                           f"FY ending {a.fy_end:%d %B %Y}. Year-to-date realised events plus estimated position.", small))
    story.append(Spacer(1,12))

    def card(label, value, sub, accent, bg):
        t = Table([[Paragraph(label, _s("cl", fontName="Helvetica-Bold", fontSize=7.5, textColor=accent))],
                   [Paragraph(value, _s("cv", fontName="Helvetica-Bold", fontSize=17, textColor=INK, leading=20))],
                   [Paragraph(sub, _s("cs", parent=small, fontSize=7))]], colWidths=[52*mm])
        t.setStyle(TableStyle([("LEFTPADDING",(0,0),(-1,-1),9),("RIGHTPADDING",(0,0),(-1,-1),9),
                               ("TOPPADDING",(0,0),(0,0),8),("BOTTOMPADDING",(0,2),(0,2),8),
                               ("TOPPADDING",(0,1),(0,2),1),("BACKGROUND",(0,0),(-1,-1),bg),
                               ("LINEABOVE",(0,0),(-1,0),2.2,accent)]))
        return t
    cards = Table([[card("YOU MADE", money(made), "Net realised gains + dividends YTD", GREEN, GREEN_BG),
                    card("YOU'LL OWE", "≈ "+money(tax["net_tax"]), "Est. extra tax from investments", ORE, ORE_BG),
                    card("YOU CAN SAVE", money(save), "If you act before 30 June — see below", BLUE, BLUE_BG)]],
                  colWidths=[56*mm,56*mm,56*mm])
    cards.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"TOP"),("LEFTPADDING",(0,0),(0,0),0),
                               ("RIGHTPADDING",(2,0),(2,0),0),("LEFTPADDING",(1,0),(2,0),5),("RIGHTPADDING",(0,0),(1,0),5)]))
    story += [cards, Spacer(1,16)]

    # 1. Realised events
    story.append(Paragraph("1 — Realised capital gains events", _s("h2", fontName="Helvetica-Bold", fontSize=12, textColor=INK)))
    story.append(Spacer(1,5))
    head = ["Holding","Acquired","Disposed","Days","Cost base","Proceeds","Gain / loss","Disc."]
    data = [[Paragraph(h, hd if i<4 else hdr) for i,h in enumerate(head)]]
    for e in sorted(cgt["events"], key=lambda x:(x.gain<0, -x.gain)):
        disc = "50%" if e.discountable else ("n/a" if e.gain < 0 else "—")
        col = GREEN if e.gain >= 0 else RED
        sign = "+" if e.gain >= 0 else ""
        data.append([Paragraph(f"{e.name}", cellb),
                     Paragraph(f"{e.acquired:%d %b %y}", cell), Paragraph(f"{e.disposed:%d %b %y}", cell),
                     Paragraph(f"{e.days_held}", cellr), Paragraph(money(e.cost_base), cellr),
                     Paragraph(money(e.proceeds), cellr),
                     Paragraph(f'<font color="#{col.hexval()[2:]}">{sign}{money(e.gain)}</font>', cellbr),
                     Paragraph(disc, cellr)])
    cw = [42*mm,17*mm,17*mm,12*mm,20*mm,20*mm,24*mm,12*mm]
    t = Table(data, colWidths=cw, repeatRows=1)
    ts = [("BACKGROUND",(0,0),(-1,0),INK),("LEFTPADDING",(0,0),(-1,-1),6),("RIGHTPADDING",(0,0),(-1,-1),6),
          ("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5),
          ("LINEBELOW",(0,1),(-1,-1),0.4,LINE),("VALIGN",(0,0),(-1,-1),"MIDDLE")]
    for i in range(2,len(data),2): ts.append(("BACKGROUND",(0,i),(-1,i),PANEL))
    t.setStyle(TableStyle(ts)); story.append(t); story.append(Spacer(1,4))
    story.append(Paragraph("Parcel method: FIFO (oldest parcels first). “Days” over 365 unlocks the 50% individual CGT discount on gains.", small))
    story.append(Spacer(1,14))

    # 2. CGT calc
    story.append(Paragraph("2 — How the net capital gain is worked out", _s("h2b", fontName="Helvetica-Bold", fontSize=12, textColor=INK)))
    story.append(Spacer(1,5))
    calc = [("Total capital gains (gross)", money(cgt["gross_gains"]), ""),
            ("Less total capital losses", money(-cgt["losses"]), "Applied to non-discount gains first to preserve the discount"),
            ("Gains after losses", money(cgt["gains_after_losses"]), ""),
            (f"Less {a.discount_rate*100:.0f}% CGT discount", money(-cgt["discount"]), "On the discount-eligible portion only"),
            ("Net capital gain (added to taxable income)", money(cgt["net_capital_gain"]), "")]
    crows = []
    for i,(l,v,c) in enumerate(calc):
        last = i==len(calc)-1
        crows.append([Paragraph(l, cellb if last else cell), Paragraph(v, cellbr if last else cellr), Paragraph(c, small)])
    ct = Table(crows, colWidths=[62*mm,26*mm,86*mm])
    ct.setStyle(TableStyle([("LEFTPADDING",(0,0),(-1,-1),6),("RIGHTPADDING",(0,0),(-1,-1),6),
                            ("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5),
                            ("VALIGN",(0,0),(-1,-1),"MIDDLE"),("LINEBELOW",(0,0),(-1,-2),0.4,LINE),
                            ("BACKGROUND",(0,len(calc)-1),(-1,len(calc)-1),GREEN_BG),
                            ("LINEABOVE",(0,len(calc)-1),(-1,len(calc)-1),0.8,GREEN)]))
    story.append(ct); story.append(Spacer(1,14))

    # 3. Income
    story.append(Paragraph("3 — Dividend income & franking credits", _s("h3", fontName="Helvetica-Bold", fontSize=12, textColor=INK)))
    story.append(Spacer(1,5))
    inc = [("Australian dividends received (cash)", money(income["au_cash"])),
           ("Franking credits (gross-up)", money(income["franking"])),
           ("Foreign dividends (AUD equiv.)", money(income["foreign_cash"])),
           ("Foreign income tax offset (US withholding)", money(income["fito"]))]
    irows = [[Paragraph("Item", hd), Paragraph("Amount", hdr)]]
    for l,v in inc: irows.append([Paragraph(l, cell), Paragraph(v, cellr)])
    it = Table(irows, colWidths=[120*mm,54*mm], repeatRows=1)
    its = [("BACKGROUND",(0,0),(-1,0),INK),("LEFTPADDING",(0,0),(-1,-1),6),("RIGHTPADDING",(0,0),(-1,-1),6),
           ("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5),("LINEBELOW",(0,1),(-1,-1),0.4,LINE)]
    for i in range(2,len(irows),2): its.append(("BACKGROUND",(0,i),(-1,i),PANEL))
    it.setStyle(TableStyle(its)); story.append(it); story.append(Spacer(1,4))
    story.append(Paragraph("Franking credits and the foreign income tax offset are <b>tax offsets</b> — they reduce tax payable dollar-for-dollar.", small))
    story.append(Spacer(1,14))

    # 4. Actions
    story.append(Paragraph("4 — Actions before 30 June " + f"{a.fy_end:%Y}", _s("h4", fontName="Helvetica-Bold", fontSize=12, textColor=INK)))
    story.append(Spacer(1,5))
    palette = {"harvest":(BLUE,BLUE_BG), "wait":(GREEN,GREEN_BG)}
    for act in actions:
        accent, bg = palette.get(act["kind"], (ORE, ORE_BG))
        title = (f"Harvest the {act['name']} loss" if act["kind"]=="harvest"
                 else f"Hold {act['name']} past the 12-month line")
        head = Paragraph(f"<b>{title}</b>", _s("ah", fontName="Helvetica-Bold", fontSize=9, textColor=accent))
        savep = Paragraph(f"save ≈ {money(act['saving'])}", _s("sv", fontName="Helvetica-Bold", fontSize=9, textColor=accent, alignment=TA_RIGHT))
        top = Table([[head, savep]], colWidths=[120*mm,40*mm])
        top.setStyle(TableStyle([("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),0),("BOTTOMPADDING",(0,0),(-1,-1),2)]))
        inner = Table([[top],[Paragraph(act["detail"], body)]], colWidths=[164*mm])
        inner.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),bg),("LEFTPADDING",(0,0),(-1,-1),10),("RIGHTPADDING",(0,0),(-1,-1),10),
                                   ("TOPPADDING",(0,0),(0,0),8),("BOTTOMPADDING",(0,-1),(0,-1),9),("TOPPADDING",(0,1),(0,1),0),
                                   ("LINEABOVE",(0,0),(-1,0),2,accent)]))
        story += [inner, Spacer(1,6)]
    story.append(Spacer(1,8))

    bl = Table([[Paragraph("Estimated net tax on investment income, after offsets and the actions above:",
                           _s("blq", fontName="Helvetica", fontSize=9.5, textColor=colors.white)),
                 Paragraph("≈ "+money(after), _s("bla", fontName="Helvetica-Bold", fontSize=18, textColor=colors.white, alignment=TA_RIGHT))]],
               colWidths=[120*mm,44*mm])
    bl.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),INK),("VALIGN",(0,0),(-1,-1),"MIDDLE"),
                            ("LEFTPADDING",(0,0),(-1,-1),12),("RIGHTPADDING",(0,0),(-1,-1),12),
                            ("TOPPADDING",(0,0),(-1,-1),12),("BOTTOMPADDING",(0,0),(-1,-1),12)]))
    story += [bl, Spacer(1,12)]
    story.append(HRFlowable(width="100%", thickness=0.5, color=LINE)); story.append(Spacer(1,5))
    story.append(Paragraph(
        "<b>For your accountant.</b> HoldCapital is a record-keeping and reporting tool providing general "
        "factual information, not personal financial, investment or tax advice. Estimates assume an indicative effective "
        f"marginal rate of {a.effective_rate*100:.0f}% (incl. Medicare levy). Verify all figures and any action with a "
        "registered tax agent before lodging. Keep CGT parcel records for at least five years.", small))
    SimpleDocTemplate(path, pagesize=A4, leftMargin=18*mm, rightMargin=18*mm,
                      topMargin=16*mm, bottomMargin=16*mm).build(story)
    return path
