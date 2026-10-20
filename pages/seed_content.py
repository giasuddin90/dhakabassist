"""The FAQs and legal pages `seed_course` loads, in Bangla and English.

Each entry holds model field values, so the command can pass it straight to
`update_or_create`. Facts here (price, free module, refund terms, payment
methods) must match the course, since the FAQ page's JSON-LD repeats them.
"""

FAQS = [
    {
        "question_bn": "সংগীতের স্বরলিপি পড়তে জানা কি জরুরি?",
        "question_en": "Do I need to know how to read music?",
        "answer_bn": "না। কোর্সটি একেবারে শুরু থেকে শেখায়, আগের কোনো জ্ঞান ধরে নেয় না।",
        "answer_en": (
            "No. The course starts from the very beginning and assumes no prior knowledge."
        ),
    },
    {
        "question_bn": "কোর্সটি কি বাংলায় না ইংরেজিতে?",
        "question_en": "Is the course in Bangla or English?",
        "answer_bn": (
            "দুটোতেই। প্রতিটি মডিউল, নোট ও কুইজ বাংলা ও ইংরেজি দুই ভাষায় আছে; "
            "যে কোনো সময় ভাষা বদলাতে পারবেন।"
        ),
        "answer_en": (
            "Both. Every module, its notes and its quiz are in Bangla and English, "
            "and you can switch language at any time."
        ),
    },
    {
        "question_bn": "কেনার আগে কি কোর্সটি দেখে নিতে পারি?",
        "question_en": "Can I try the course before buying?",
        "answer_bn": (
            "হ্যাঁ। একটি ফ্রি অ্যাকাউন্ট খুললেই মডিউল 1 আপনার। মডিউল 2 থেকে এগোতে "
            "চাইলে তখন এনরোল করুন।"
        ),
        "answer_en": (
            "Yes. Create a free account and Module 1 is yours. Enroll when you want to "
            "continue to Module 2."
        ),
    },
    {
        "question_bn": "কতদিন অ্যাক্সেস থাকবে?",
        "question_en": "How long do I have access?",
        "answer_bn": "আজীবন। নিজের গতিতে পড়ুন, যখন ইচ্ছা ফিরে আসুন।",
        "answer_en": "Lifetime access. Study at your own pace and return whenever you like.",
    },
    {
        "question_bn": "কীভাবে পেমেন্ট করব?",
        "question_en": "How do I pay?",
        "answer_bn": (
            "বিকাশ, নগদ, ভিসা ও মাস্টারকার্ড। আন্তর্জাতিক কার্ডও গ্রহণ করা হয়। "
            "পেমেন্ট নিশ্চিত হলেই আপনি স্বয়ংক্রিয়ভাবে এনরোল হয়ে যাবেন।"
        ),
        "answer_en": (
            "bKash, Nagad, Visa and Mastercard. International cards are also accepted. "
            "You are enrolled automatically once payment is confirmed."
        ),
    },
    {
        "question_bn": "আরও কোর্স আসবে কি?",
        "question_en": "Will there be more courses?",
        "answer_bn": (
            "সংগীতের ভিত্তির পর্ব 2 তৈরি হচ্ছে। পর্ব 1 শেষ করা শিক্ষার্থীরা এটি "
            "সবার আগে পাবেন।"
        ),
        "answer_en": (
            "Part 2 of Foundations of Music is in production. Students who finish "
            "Part 1 will be offered it first."
        ),
    },
]

TERMS_BN = """\
## আমরা কারা

DhakaBassist পরিচালনা করেন তানভীর হক, ঢাকা, বাংলাদেশ। এই ওয়েবসাইটের মাধ্যমে
করা প্রতিটি কেনাকাটায় এই শর্তাবলি প্রযোজ্য।

## আপনার অ্যাকাউন্ট

পাসওয়ার্ড গোপন রাখা এবং আপনার অ্যাকাউন্টের সব কার্যকলাপের দায়িত্ব আপনার।
একটি অ্যাকাউন্ট একজন ব্যক্তির জন্য; কোর্সের অ্যাক্সেস শেয়ার, পুনরায় বিক্রি
বা হস্তান্তর করা যাবে না।

## কোর্স

এনরোল করলে আপনি একটি ব্যক্তিগত, অহস্তান্তরযোগ্য লাইসেন্স পান: কোর্সটি যতদিন
এই প্ল্যাটফর্মে থাকবে, ততদিন আপনি এর উপকরণ পড়তে পারবেন। ভিডিও, অডিও,
স্বরলিপি, লিখিত নোট ও ওয়ার্কশিটের কপিরাইট তানভীর হকের। নিজের পড়াশোনার জন্য
দেওয়া ওয়ার্কশিট ডাউনলোড করতে পারবেন। কোর্সের কোনো অংশ পুনর্বিতরণ, প্রকাশ,
পুনরায় বিক্রি বা জনসমক্ষে পরিবেশন করা যাবে না।

## পেমেন্ট

দাম বাংলাদেশি টাকায়, গেটওয়ে ফি সহ। পেমেন্ট সামলায় আমাদের পেমেন্ট প্রোভাইডার;
আমরা কখনো আপনার কার্ডের তথ্য পাই না বা সংরক্ষণ করি না। পেমেন্ট নিশ্চিত হলেই
স্বয়ংক্রিয়ভাবে অ্যাক্সেস চালু হয়।

## প্রাপ্যতা

আমরা প্ল্যাটফর্মটি সবসময় চালু রাখার চেষ্টা করি, তবে নিরবচ্ছিন্ন অ্যাক্সেসের
নিশ্চয়তা দিই না। কোর্সের বিষয়বস্তু সংশোধন, উন্নত বা সম্প্রসারিত হতে পারে।

## পরিবর্তন

আমরা এই শর্তাবলি হালনাগাদ করতে পারি। গুরুত্বপূর্ণ পরিবর্তন এই পাতায় জানানো
হবে, আর নিচের তারিখ সবসময় দেখায় শর্তাবলি শেষ কবে বদলেছে।

## যোগাযোগ

এই শর্তাবলি নিয়ে প্রশ্ন থাকলে: hello@dhakabassist.com
"""

TERMS_EN = """\
## Who we are

DhakaBassist is operated by Tanveer Haque, Dhaka, Bangladesh. These terms apply
to every purchase made through this website.

## Your account

You are responsible for keeping your password confidential and for activity on
your account. One account is for one person; course access may not be shared,
resold or transferred.

## The course

Enrolment grants you a personal, non-transferable licence to study the course
material for as long as the course remains available on this platform. Videos,
audio, notation, written notes and worksheets remain the copyright of Tanveer
Haque. You may download the worksheets provided for your own study. You may not
redistribute, publish, resell or publicly perform any part of the course.

## Payment

Prices are in Bangladeshi Taka and include any gateway fee. Payment is handled
by our payment provider; we never receive or store your card details. Access is
granted automatically once payment is confirmed.

## Availability

We aim to keep the platform available at all times, but we do not guarantee
uninterrupted access. Course content may be corrected, improved or extended.

## Changes

We may update these terms. Material changes will be announced on this page, and
the date below always shows when the terms last changed.

## Contact

Questions about these terms: hello@dhakabassist.com
"""

PRIVACY_BN = """\
## আমরা কী সংগ্রহ করি

- **আপনার অ্যাকাউন্ট**: নাম, ইমেইল ঠিকানা ও হ্যাশ করা পাসওয়ার্ড। পাসওয়ার্ড
  একমুখী হ্যাশ হিসেবে রাখা হয়, আমরা তা পড়তে পারি না।
- **আপনার পড়াশোনা**: কোন মডিউল খুলেছেন ও শেষ করেছেন, কুইজের উত্তর এবং ভিডিও
  কোথায় থামিয়েছেন, যাতে পরের বার আপনার অগ্রগতি সেখানেই থাকে।
- **আপনার অর্ডার**: টাকার পরিমাণ, বেছে নেওয়া পেমেন্ট পদ্ধতি এবং পেমেন্ট
  প্রোভাইডারের দেওয়া রেফারেন্স। আপনার কার্ড নম্বর আমরা কখনো পাই না বা রাখি না।

## কেন সংগ্রহ করি

আপনার কেনা কোর্সে অ্যাক্সেস দিতে, অগ্রগতি দেখাতে, সহায়তার প্রশ্নের উত্তর দিতে
এবং হিসাবরক্ষণের আইনি বাধ্যবাধকতা মানতে। আমরা আপনার তথ্য বিক্রি করি না এবং
বিজ্ঞাপনের জন্য কারও সাথে শেয়ার করি না।

## আর কে এই তথ্য ব্যবহার করে

আমাদের পেমেন্ট প্রোভাইডার আপনার পেমেন্ট প্রক্রিয়া করে। হোস্টিং ও ইমেইল
প্রোভাইডার চুক্তির অধীনে আমাদের হয়ে তথ্য প্রক্রিয়া করে। কোর্সের ভিডিও একটি
স্ট্রিমিং প্রোভাইডারের মাধ্যমে দেখানো হতে পারে।

## কতদিন রাখি

অ্যাকাউন্ট ও অগ্রগতির তথ্য, যতদিন আপনার অ্যাকাউন্ট আছে। অর্ডারের রেকর্ড, কর
আইন যতদিন চায়। যে কোনো সময় অ্যাকাউন্ট মুছে ফেলতে বলতে পারেন; আইনত যেসব অর্ডার
রেকর্ড রাখতে হয়, সেগুলো রাখা হবে।

## আপনার অধিকার

অ্যাকাউন্ট সেটিংসে আপনার তথ্য দেখতে ও ঠিক করতে পারবেন, তথ্যের একটি কপি
ডাউনলোড করতে পারবেন, অথবা অ্যাকাউন্ট মুছে ফেলতে বলতে পারবেন।
hello@dhakabassist.com-এ ইমেইল করুন, আমরা দুই কর্মদিবসের মধ্যে উত্তর দেব।

## কুকি

আপনাকে সাইন ইন রাখতে একটি সেশন কুকি এবং ফর্মকে ক্রস-সাইট রিকোয়েস্ট ফোর্জারি
থেকে রক্ষা করতে একটি কুকি ব্যবহার করি। কোনোটিই ট্র্যাকিং বা বিজ্ঞাপনের জন্য নয়।
"""

PRIVACY_EN = """\
## What we collect

- **Your account**: name, email address and a hashed password. Passwords are
  stored as one-way hashes and cannot be read by us.
- **Your learning**: which modules you have opened and completed, your quiz
  answers and where you paused a video, so your progress is there next time.
- **Your orders**: the amount, the method you chose and the reference our
  payment provider returns. We never receive or store your card number.

## Why we collect it

To give you access to what you bought, to show your progress, to answer support
questions and to meet our accounting obligations. We do not sell your data and
we do not share it for advertising.

## Who else processes it

Our payment provider processes your payment. Our hosting and email providers
process data on our behalf under contract. Course videos may be delivered by a
streaming provider.

## How long we keep it

Account and progress data for as long as your account exists. Order records for
as long as tax law requires. You may ask us to delete your account at any time;
order records are retained where we are legally required to keep them.

## Your rights

You can see and correct your details in your account settings, download a copy
of your data, or ask us to delete your account. Email hello@dhakabassist.com and
we will reply within two working days.

## Cookies

We use one session cookie to keep you signed in and one cookie to protect forms
against cross-site request forgery. Neither is used for tracking or
advertising.
"""

REFUNDS_BN = """\
## সংক্ষেপে

কেনার **7 দিনের** মধ্যে, যদি **দুটির কম মডিউল** শেষ করে থাকেন, পুরো টাকা ফেরত
পাবেন।

## কেন এই শর্ত

মডিউল 1 ফ্রি, যাতে টাকা দেওয়ার আগেই সিদ্ধান্ত নিতে পারেন। কয়েকটি মডিউল পড়া
হয়ে গেলে উপকরণ আপনার কাছে পৌঁছে গেছে।

## কীভাবে রিফান্ড চাইবেন

আপনার অ্যাকাউন্টের ইমেইল থেকে hello@dhakabassist.com-এ অর্ডার নম্বরসহ ইমেইল
করুন। কারণ জানানোর দরকার নেই। আমরা দুই কর্মদিবসের মধ্যে উত্তর দিই।

## টাকা কীভাবে ফেরত যায়

পেমেন্ট প্রোভাইডারের মাধ্যমে যে পদ্ধতিতে পেমেন্ট করেছিলেন সেখানেই টাকা ফেরত
যায়। বিকাশ ও নগদে সাধারণত কয়েক কর্মদিবস লাগে; কার্ডে আপনার ব্যাংকভেদে দশ দিন
পর্যন্ত লাগতে পারে।

## ব্যতিক্রম

প্ল্যাটফর্মের কোনো ত্রুটির কারণে পড়তে না পারলে, অথবা ভুল করে বা দুবার পেমেন্ট
হয়ে গেলে, এই শর্তের বাইরেও আমরা রিফান্ড বিবেচনা করব। এখানে লেখা কিছুই আপনার
আইনগত অধিকার সীমিত করে না।
"""

REFUNDS_EN = """\
## The short version

You can have your money back within **7 days** of purchase if you have
completed **fewer than two modules**.

## Why that condition

Module 1 is free precisely so you can decide before paying. Once several modules
have been studied, the material has been delivered.

## How to request a refund

Email hello@dhakabassist.com from the address on your account, quoting your
order number. You do not need to give a reason. We reply within two working
days.

## How the money is returned

Refunds go back to the original payment method through our payment provider.
bKash and Nagad usually settle within a few working days; card refunds can take
up to ten, depending on your bank.

## Exceptions

We will consider a refund outside these conditions if the platform failed in a
way that prevented you from studying, or where a payment was made in error or
duplicated. Nothing here limits any statutory right you have.
"""

LEGAL_PAGES = {
    "terms": {
        "title_bn": "শর্তাবলি",
        "title_en": "Terms & Conditions",
        "meta_description_bn": (
            "DhakaBassist কোন শর্তে তার অনলাইন সংগীত তত্ত্বের কোর্স বিক্রি ও সরবরাহ করে।"
        ),
        "meta_description_en": (
            "The terms under which DhakaBassist sells and delivers its online music "
            "theory courses."
        ),
        "body_markdown_bn": TERMS_BN,
        "body_markdown_en": TERMS_EN,
    },
    "privacy": {
        "title_bn": "গোপনীয়তা নীতি",
        "title_en": "Privacy Policy",
        "meta_description_bn": (
            "DhakaBassist কোন ব্যক্তিগত তথ্য সংগ্রহ করে, কেন করে এবং কতদিন রাখে।"
        ),
        "meta_description_en": (
            "What personal data DhakaBassist collects, why, and how long it is kept."
        ),
        "body_markdown_bn": PRIVACY_BN,
        "body_markdown_en": PRIVACY_EN,
    },
    "refunds": {
        "title_bn": "রিফান্ড নীতি",
        "title_en": "Refund Policy",
        "meta_description_bn": (
            "DhakaBassist-এর কোর্স কেনার টাকা কখন ফেরত পাওয়া যায় এবং কীভাবে চাইবেন।"
        ),
        "meta_description_en": (
            "When a DhakaBassist course purchase can be refunded, and how to ask."
        ),
        "body_markdown_bn": REFUNDS_BN,
        "body_markdown_en": REFUNDS_EN,
    },
}
