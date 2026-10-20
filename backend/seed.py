"""
Seed the database with 4 demo dreaded tasks so the app is usable immediately.
Only runs when the database is empty — safe to call on every startup.
"""
from __future__ import annotations

import asyncio

from backend import database as db

# ---------------------------------------------------------------------------
# Demo task definitions
# ---------------------------------------------------------------------------

DEMO_TASKS = [
    # 1 — Dentist letter
    {
        "raw_text": "Reply to my dentist's scary letter",
        "context_text": (
            "The letter says I have a cavity that needs urgent attention "
            "and I should schedule an appointment or it will get worse. "
            "I've been avoiding it for three weeks."
        ),
        "dread_score": 7,
        "dread_reason": "Fear of bad news and confronting a problem that feels overwhelming",
        "first_step": "Open the letter and read just the first paragraph",
        "first_step_duration_min": 2,
        "ladder": [
            {"description": "Write down what the letter is asking me to do", "duration_min": 3},
            {"description": "Look up the dentist's phone number or email", "duration_min": 2},
            {"description": "Draft a short reply or prepare what to say on the phone", "duration_min": 5},
            {"description": "Send the reply or make the call", "duration_min": 5},
        ],
        "prepared_artifacts": [
            {
                "type": "email_draft",
                "title": "Reply to Dentist Letter",
                "content": (
                    "Subject: Re: Your Recent Letter — Appointment Scheduling\n\n"
                    "Dear Dr. [Name],\n\n"
                    "Thank you for your letter. I'd like to schedule an appointment "
                    "to discuss the cavity you mentioned.\n\n"
                    "Could you please let me know your available times in the next "
                    "two weeks? My preferred times are [morning/afternoon] on [days].\n\n"
                    "Please feel free to reply by email or reach me at [your phone number].\n\n"
                    "Thank you,\n[Your Name]"
                ),
            },
            {
                "type": "checklist",
                "title": "Before the Dentist Appointment",
                "content": (
                    "□ Find dental insurance card\n"
                    "□ Note any tooth sensitivity or pain to mention\n"
                    "□ Write down questions to ask the dentist\n"
                    "□ Confirm appointment time 24 hours before\n"
                    "□ Arrange transport if needed"
                ),
            },
        ],
        "is_mlf": False,
    },
    # 2 — Expenses
    {
        "raw_text": "File last month's expenses",
        "context_text": (
            "I have receipts scattered everywhere — some paper, some phone photos. "
            "My employer needs them by end of this month or I won't get reimbursed."
        ),
        "dread_score": 6,
        "dread_reason": "Boring paperwork with an unclear starting point",
        "first_step": "Open the expenses app (or a new spreadsheet tab)",
        "first_step_duration_min": 2,
        "ladder": [
            {"description": "Gather all paper receipts into one pile", "duration_min": 5},
            {"description": "Check phone for receipt photos — save them to one album", "duration_min": 5},
            {"description": "Enter the 3 largest expenses first", "duration_min": 10},
            {"description": "Enter remaining smaller expenses", "duration_min": 10},
            {"description": "Submit the completed expense report", "duration_min": 3},
        ],
        "prepared_artifacts": [
            {
                "type": "checklist",
                "title": "Expense Filing Checklist",
                "content": (
                    "GATHER RECEIPTS:\n"
                    "□ Paper receipts from wallet / bag\n"
                    "□ Paper receipts from desk / drawers\n"
                    "□ Photos of receipts on phone\n"
                    "□ Email receipts (search 'receipt' in inbox)\n"
                    "□ Bank statement for anything missing\n\n"
                    "FOR EACH RECEIPT:\n"
                    "□ Date\n"
                    "□ Amount\n"
                    "□ Category (meals, transport, supplies, other)\n"
                    "□ Business reason / client name\n\n"
                    "SUBMISSION:\n"
                    "□ Total matches bank statement?\n"
                    "□ All receipts attached or photographed?\n"
                    "□ Manager approval needed?\n"
                    "□ Deadline: ___________"
                ),
            }
        ],
        "is_mlf": False,
    },
    # 3 — Insurance call
    {
        "raw_text": "Call the insurance company about my disputed claim",
        "context_text": (
            "They denied my claim for $340 of physio sessions. "
            "The denial letter says it wasn't 'medically necessary' "
            "but my doctor prescribed it. I need to appeal."
        ),
        "dread_score": 8,
        "dread_reason": "Awkward conversation with authority — fear of confrontation and rejection",
        "first_step": "Find and write down the claim number from the denial letter",
        "first_step_duration_min": 2,
        "ladder": [
            {"description": "Read the denial letter and highlight the specific reason given", "duration_min": 5},
            {"description": "Gather your doctor's referral or prescription for physio", "duration_min": 5},
            {"description": "Read the phone script and highlight any lines you'll need", "duration_min": 5},
            {"description": "Call the number on the letter during business hours", "duration_min": 10},
        ],
        "prepared_artifacts": [
            {
                "type": "phone_script",
                "title": "Insurance Appeal Phone Script",
                "content": (
                    "BEFORE YOU CALL, HAVE READY:\n"
                    "- Your policy number\n"
                    "- The claim number (on the denial letter)\n"
                    "- The denial letter itself\n"
                    "- Your doctor's referral / prescription\n\n"
                    "OPENING:\n"
                    '"Hello, I\'m calling to appeal a claim denial. '
                    "My policy number is [NUMBER] and the claim number is [CLAIM#]. "
                    'I received a denial letter dated [DATE]."\n\n'
                    "IF ASKED WHY YOU'RE APPEALING:\n"
                    '"My doctor prescribed physiotherapy as medically necessary. '
                    "I have a referral from Dr. [Name]. "
                    'The sessions were directly related to [your condition]."\n\n'
                    "IF THEY SAY IT'S NOT COVERED:\n"
                    '"I\'d like to formally appeal this decision. '
                    "Can you please tell me the appeals process and the address "
                    'to send supporting documentation?"\n\n'
                    "CLOSE:\n"
                    '"Can I get a reference number for this call? '
                    'And what\'s the timeline for the appeal decision?"\n\n'
                    "NOTES (fill in during the call):\n"
                    "Person I spoke to: _______________\n"
                    "Reference #: _______________\n"
                    "Next steps: _______________\n"
                    "Appeal deadline: _______________"
                ),
            }
        ],
        "is_mlf": False,
    },
    # 4 — Big report
    {
        "raw_text": "Start reading that 80-page quarterly report my manager sent",
        "context_text": (
            "It's been sitting in my inbox for two weeks. "
            "I have a meeting about it next Tuesday. "
            "I don't even know where to start — the whole thing feels like a wall of text."
        ),
        "dread_score": 5,
        "dread_reason": "Feels overwhelming in scope — unclear entry point",
        "first_step": "Open the report and read just the executive summary (first 1-2 pages)",
        "first_step_duration_min": 2,
        "ladder": [
            {"description": "Read the table of contents and circle the 3 most relevant sections", "duration_min": 5},
            {"description": "Read section 1 fully, take 3 bullet-point notes", "duration_min": 10},
            {"description": "Read the two circled sections", "duration_min": 10},
            {"description": "Write 5 bullet points summarising the whole report", "duration_min": 10},
            {"description": "Prepare 2 talking points or questions for the meeting", "duration_min": 5},
        ],
        "prepared_artifacts": [
            {
                "type": "outline",
                "title": "80-Page Report — Reading Guide",
                "content": (
                    "HOW TO READ AN 80-PAGE REPORT WITHOUT LOSING YOUR MIND:\n\n"
                    "PHASE 1 — ORIENT (5 min):\n"
                    "• Read the executive summary\n"
                    "• Scan the table of contents\n"
                    "• Mark the 3 sections most relevant to your role\n\n"
                    "PHASE 2 — SKIM STRATEGICALLY (15 min):\n"
                    "• Read section headings and first paragraph of each\n"
                    "• Look at all charts, graphs, and tables — they tell the story faster\n"
                    "• Mark sections to read in full\n\n"
                    "PHASE 3 — DEEP READ WHAT MATTERS:\n"
                    "• Read 2-3 sections most relevant to Tuesday's meeting\n"
                    "• Notes format: [Section] → [Key finding] → [What it means for us]\n\n"
                    "PHASE 4 — MEETING PREP:\n"
                    "• What is the report's main conclusion?\n"
                    "• What decision does it support?\n"
                    "• What questions might your manager ask?\n"
                    "• Your recommendation in one sentence:\n"
                    '  "The report shows [X]. I think we should [action] because [reason]."\n'
                ),
            }
        ],
        "is_mlf": False,
    },
]


# ---------------------------------------------------------------------------
# Seed function
# ---------------------------------------------------------------------------

async def seed_if_empty() -> None:
    """Insert demo tasks only when the database has no tasks yet."""
    existing = await db.get_all_tasks()
    if existing:
        return   # Already seeded — do nothing

    for t in DEMO_TASKS:
        task_id = await db.create_task(
            raw_text=t["raw_text"],
            context_text=t.get("context_text"),
            dread_score=t["dread_score"],
            dread_reason=t["dread_reason"],
            first_step=t["first_step"],
            ladder=t["ladder"],
            prepared_artifacts=t["prepared_artifacts"],
            is_mlf=t["is_mlf"],
        )
        await db.create_steps_for_task(
            task_id=task_id,
            first_step=t["first_step"],
            first_step_duration=t["first_step_duration_min"],
            ladder=t["ladder"],
        )


if __name__ == "__main__":
    asyncio.run(seed_if_empty())
