"""Seed the six Learn-module lessons.

Idempotent: lessons are matched by slug and updated in place, so re-running
is safe. Static content, DB-stored — no CMS (per the architecture).

Usage: .venv/Scripts/python.exe manage.py seed_lessons
"""
from django.core.management.base import BaseCommand

from learn.models import Lesson, validate_quiz_questions

LESSONS = [
    {
        "order": 1,
        "title": "Budgeting Basics",
        "slug": "budgeting-basics",
        "summary": "Know where your money goes: track income, plan spending, and apply the 50/30/20 rule.",
        "content": """
<p>Money rarely runs out all at once — it leaks. A budget is simply a plan
that decides where your money goes <em>before</em> the month starts,
instead of wondering where it went at the end of it.</p>

<h3>The 50/30/20 rule</h3>
<p>A simple starting point for your first budget:</p>
<ul>
  <li><strong>50% — Needs.</strong> Rent, groceries, utilities, transport, minimum debt payments.</li>
  <li><strong>30% — Wants.</strong> Dining out, subscriptions, hobbies, shopping.</li>
  <li><strong>20% — Savings &amp; debt payoff.</strong> Emergency fund, investments, extra debt payments.</li>
</ul>

<h3>Two habits that make budgets work</h3>
<ul>
  <li><strong>Track every expense</strong> for a week before you plan — real numbers beat guesses.</li>
  <li><strong>Budget for a zero sum</strong>: income − expenses − savings = 0. Every rupee has a job.</li>
</ul>

<p>A budget isn't a cage — it's permission to spend without guilt, because
you already decided what the money is for.</p>
""",
        "quiz_questions": {
            "questions": [
                {
                    "question": "In the 50/30/20 rule, what should 50% of your income cover?",
                    "options": ["Wants", "Needs", "Savings", "Investments"],
                    "correct": 1,
                },
                {
                    "question": "A budget is best described as…",
                    "options": [
                        "A record of what you already spent",
                        "A plan for your money before the month starts",
                        "A list of things you can't buy",
                        "A bank feature you have to pay for",
                    ],
                    "correct": 1,
                },
                {
                    "question": "Which of these counts as a “need”?",
                    "options": ["Streaming subscription", "Dining out", "Rent", "A new phone"],
                    "correct": 2,
                },
            ]
        },
    },
    {
        "order": 2,
        "title": "Saving & Emergency Funds",
        "slug": "saving-emergency-funds",
        "summary": "Pay yourself first and build a 3–6 month safety net before anything else.",
        "content": """
<p>An emergency fund is the difference between a surprise being annoying and
a surprise being a crisis. It's cash you can reach immediately, for
unexpected expenses only — a medical bill, a repair, a job gap.</p>

<h3>How much is enough?</h3>
<p>Most experts suggest <strong>3–6 months of essential expenses</strong>.
Start smaller: a ₹10,000 starter fund is already real protection, then
grow it over time.</p>

<h3>Pay yourself first</h3>
<p>Automate it: the moment your salary lands, move your savings target to a
separate account. If saving happens before spending, you never have to
"find" money to save at the end of the month.</p>

<h3>Where to keep it</h3>
<ul>
  <li><strong>Liquid and safe</strong> — a savings account or liquid fund, not stocks.</li>
  <li><strong>Separate from spending money</strong>, so you don't treat it as a pool for impulse buys.</li>
  <li><strong>Not your investments</strong> — emergency money must not depend on market timing.</li>
</ul>
""",
        "quiz_questions": {
            "questions": [
                {
                    "question": "How many months of expenses should a full emergency fund cover?",
                    "options": ["1 month", "3–6 months", "12 months", "2 years"],
                    "correct": 1,
                },
                {
                    "question": "“Pay yourself first” means…",
                    "options": [
                        "Buying what you want before bills",
                        "Moving savings to a separate account before spending",
                        "Getting a second job",
                        "Paying the highest salary to yourself",
                    ],
                    "correct": 1,
                },
                {
                    "question": "Where should an emergency fund live?",
                    "options": [
                        "A liquid savings account",
                        "Stock market",
                        "A locked 5-year deposit",
                        "Under the mattress",
                    ],
                    "correct": 0,
                },
            ]
        },
    },
    {
        "order": 3,
        "title": "Understanding Debt & Credit",
        "slug": "understanding-debt-credit",
        "summary": "Good debt vs bad debt, how APR works, and what moves your credit score.",
        "content": """
<p>Debt is a tool — useful when it buys something that grows in value, and
expensive when it buys things that shrink. The difference is the interest
rate and what you're borrowing for.</p>

<h3>Good debt vs bad debt</h3>
<ul>
  <li><strong>Good debt</strong>: a home loan, an education loan — the asset usually outlives the loan.</li>
  <li><strong>Bad debt</strong>: credit card balances on everyday spending, which compound at high rates.</li>
</ul>

<h3>APR is the real price</h3>
<p>APR (Annual Percentage Rate) is the yearly cost of borrowing, including
fees. A “0% interest” offer with a big fee can be more expensive than a
loan with a transparent rate — always compare APR, not the headline number.</p>

<h3>Your credit score</h3>
<ul>
  <li>Built slowly, by <strong>paying on time</strong> and keeping balances low.</li>
  <li>Check your report for errors — a wrong default can quietly raise your borrowing costs.</li>
  <li>Missing a payment hurts far more than a small balance helps.</li>
</ul>
""",
        "quiz_questions": {
            "questions": [
                {
                    "question": "APR stands for…",
                    "options": [
                        "Annual Percentage Rate",
                        "Applied Payment Ratio",
                        "Average Portfolio Return",
                        "Automatic Payment Rule",
                    ],
                    "correct": 0,
                },
                {
                    "question": "Which of these is generally the most expensive debt?",
                    "options": ["Home loan", "Education loan", "Credit card balance", "Car loan"],
                    "correct": 2,
                },
                {
                    "question": "What most reliably improves a credit score?",
                    "options": [
                        "Closing old accounts",
                        "Paying bills on time",
                        "Checking your score often",
                        "Using many cards at once",
                    ],
                    "correct": 1,
                },
            ]
        },
    },
    {
        "order": 4,
        "title": "Investing Fundamentals",
        "slug": "investing-fundamentals",
        "summary": "Risk and return, compounding, and why diversification is the only free lunch.",
        "content": """
<p>Investing is how money makes money. The two ideas that matter most:
<strong>compounding</strong> (earnings earning their own earnings) and
<strong>diversification</strong> (not betting everything on one thing).</p>

<h3>Risk and return</h3>
<p>Higher expected returns come with higher risk and more volatility. Over
long horizons, equities have historically outgrown cash — but you must be
able to leave the money alone while the market does its thing.</p>

<h3>Compounding, in one sentence</h3>
<p>If you earn a return, and that return earns a return, growth becomes
exponential. Starting early beats starting big: time is the investor's
best friend.</p>

<h3>Diversification</h3>
<ul>
  <li>Spread across asset classes (stocks, bonds, cash) and sectors.</li>
  <li>A broad index fund gives you the whole market's growth with a single purchase.</li>
  <li>Don't put money you need in the next 3–5 years into volatile assets.</li>
</ul>

<p>You don't need to be clever — you need to be consistent.</p>
""",
        "quiz_questions": {
            "questions": [
                {
                    "question": "Diversification means…",
                    "options": [
                        "Investing only in one big company",
                        "Spreading money across many investments",
                        "Trading every day",
                        "Keeping everything in cash",
                    ],
                    "correct": 1,
                },
                {
                    "question": "Compounding is powerful because…",
                    "options": [
                        "Returns start earning their own returns",
                        "It removes all risk",
                        "It guarantees profits",
                        "It only works with large amounts",
                    ],
                    "correct": 0,
                },
                {
                    "question": "Historically, which has offered the highest long-term returns?",
                    "options": ["Savings account", "Gold", "Equities (stock market)", "Fixed deposits"],
                    "correct": 2,
                },
            ]
        },
    },
    {
        "order": 5,
        "title": "Taxes & Your First Job",
        "slug": "taxes-first-job",
        "summary": "Gross vs net pay, TDS, tax slabs, and the deductions that quietly save you money.",
        "content": """
<p>Your offer letter shows one number; your bank account shows another.
Understanding the gap is the first step to planning around it.</p>

<h3>Gross vs net</h3>
<p><strong>Gross</strong> is what you're offered. <strong>Net</strong> is
what lands in your account after tax deducted at source (TDS), provident
fund, and other deductions. Plan your budget around net pay.</p>

<h3>Tax slabs and deductions</h3>
<ul>
  <li>Income tax is progressive — different slices of income are taxed at different rates.</li>
  <li>Deductions (like Section 80C investments in India) reduce the taxable slice, not just the tax itself.</li>
  <li>Keep Form 16 and investment proofs — you'll need them when filing.</li>
</ul>

<h3>File on time</h3>
<p>Filing is not optional. Late filings can mean interest and penalties
even when no tax is due. A 30-minute effort once a year protects you from
a much larger headache later.</p>
""",
        "quiz_questions": {
            "questions": [
                {
                    "question": "TDS stands for…",
                    "options": [
                        "Total Deduction Scheme",
                        "Tax Deducted at Source",
                        "Tax Deferred Savings",
                        "Transfer of Deductions",
                    ],
                    "correct": 1,
                },
                {
                    "question": "Gross pay minus deductions equals…",
                    "options": ["Taxable income", "Net pay", "Annual CTC", "Tax refund"],
                    "correct": 1,
                },
                {
                    "question": "Which of these reduces your taxable income?",
                    "options": [
                        "Section 80C investments",
                        "Credit card EMI",
                        "Rent paid in cash",
                        "Eating out",
                    ],
                    "correct": 0,
                },
            ]
        },
    },
    {
        "order": 6,
        "title": "Reading a Portfolio",
        "slug": "reading-a-portfolio",
        "summary": "Asset allocation, benchmarks, and rebalancing — how to actually read an investment statement.",
        "content": """
<p>A portfolio statement is a story about your money's job. Reading it means
looking past the total and asking: <em>what am I holding, how risky is it,
and is it still my plan?</em></p>

<h3>Asset allocation is the plot</h3>
<p>The mix of asset classes — equities, debt, cash — drives most of your
long-term returns and nearly all of your risk. A 60/40 stock/bond split
and a 100% stock portfolio are different investments, even with the same
total.</p>

<h3>Compare to a benchmark</h3>
<p>A single month's return tells you little. Compare your performance to a
relevant index over a year or more. Beating the benchmark by a little is
fine; matching it is honestly very good.</p>

<h3>Rebalancing</h3>
<ul>
  <li>Over time, winners drift your allocation off target.</li>
  <li>Rebalancing = selling a bit of what grew and buying what lagged, back to your plan.</li>
  <li>It forces you to buy low and sell high without predicting anything.</li>
</ul>

<p>Check your portfolio on a schedule — quarterly is plenty — and read the
allocation before the returns.</p>
""",
        "quiz_questions": {
            "questions": [
                {
                    "question": "Asset allocation refers to…",
                    "options": [
                        "How often you trade",
                        "Your mix of asset classes",
                        "The total value of your account",
                        "Which broker you use",
                    ],
                    "correct": 1,
                },
                {
                    "question": "A benchmark is…",
                    "options": [
                        "A guaranteed return",
                        "A reference index used to compare performance",
                        "The minimum investment amount",
                        "A type of tax",
                    ],
                    "correct": 1,
                },
                {
                    "question": "Rebalancing means…",
                    "options": [
                        "Selling everything and starting over",
                        "Restoring your portfolio to its target allocation",
                        "Moving to a new broker",
                        "Adding more cash every month",
                    ],
                    "correct": 1,
                },
            ]
        },
    },
]


class Command(BaseCommand):
    help = "Seed the six Learn-module lessons (idempotent by slug)."

    def handle(self, *args, **options):
        created, updated = 0, 0
        for data in LESSONS:
            if not validate_quiz_questions(data["quiz_questions"]):
                raise ValueError(f"Invalid quiz structure for {data['title']}")
            lesson, was_created = Lesson.objects.get_or_create(
                slug=data["slug"], defaults={k: v for k, v in data.items() if k != "slug"}
            )
            if was_created:
                created += 1
            else:
                for key, value in data.items():
                    setattr(lesson, key, value)
                lesson.save(update_fields=[k for k in data if k != "slug"])
                updated += 1
        self.stdout.write(
            self.style.SUCCESS(f"Lessons: {created} created, {updated} updated ({len(LESSONS)} total).")
        )
