# Antex Analytics Portal

Antex uchun Superset boshqaruv portalining boshlang'ich versiyasi.

## Imkoniyatlar

- Antex logotipi bilan animatsiyali bosh sahifa
- Sessiya asosidagi admin autentifikatsiyasi
- Foydalanuvchilarni yaratish, tahrirlash, faollashtirish va o'chirish
- Admin, muharrir va kuzatuvchi rollari
- Superset REST API orqali datasetlarni sinxronlash, yaratish, tahrirlash va o'chirish
- Superset datasetlarini portal ichidagi papkalar va taglar bilan tartiblash
- Metabase querylarini collectionlar bo'yicha ko'rish va qidirish
- Metabase querylarini tahrirlash, nusxalash, ko'chirish va Trash bo'limiga o'tkazish
- Metabase collection daraxtida ishlash, yangi papka va SQL query yaratish

## Ishga tushirish

```bash
cp .env.example .env
docker compose up -d --build
```

`.env` faylida Superset uchun `SUPERSET_URL`, `SUPERSET_USERNAME`,
`SUPERSET_PASSWORD`, Metabase uchun esa `METABASE_URL`, `METABASE_USERNAME`,
`METABASE_PASSWORD` qiymatlari berilishi kerak.

Ilova standart holatda `127.0.0.1:8108` manziliga bog'lanadi.

## Hisobotlarni tekshirish

Admin menyusidagi `Проверка отчётов` bo'limiga faqat tagsiz dashboardlar
alohida qo'shiladi. Qo'shish va tasdiqlash biznes-tag bermaydi. Kompaniya
tanlash serverdagi guest token RLS orqali bajariladi (`company_id = ID`).
Dashboard chartlari va native filtr datasetlarida `company_id` bo'lishi shart.

Avval kompaniya va dashboardni oching, natijalarni tekshiring va `Проверено`
belgilang. `Одобрить` joriy dashboard, chart va SQL versiyasini tasdiqlaydi.
`Опубликовать` alohida tasdiq bilan tanlangan tagni biriktiradi. Tasdiqdan
keyingi o'zgarish qayta tekshiruvni talab qiladi. Izohlar va amallar saqlanadi.
Nashr qilingan hisobotni yangilash uchun tagsiz alohida dashboard va chart/dataset
nusxalaridan foydalaning; portal nashr qilingan dashboardni tahrirlamaydi.

Serverdagi Superset xizmat foydalanuvchisiga dashboard/chart/dataset o'qish,
embedding sozlash, guest token berish, tag/publish va kompaniyalar ro'yxatini
SELECT qilish ruxsatlari kerak. `REVIEW_DATABASE_ID` va `REVIEW_EMBED_ORIGIN`
joylangan muhitga mos bo'lishi kerak. Guest token berish ruxsati oddiy portal
foydalanuvchilariga berilmaydi. SQL Lab API faqat serverdan qat'iy SELECT uchun
chaqiriladi; brauzerga xizmat login/paroli berilmaydi.

```bash
python -m unittest discover -s tests -v
```

Superset SDK 0.4.0 lokal static asset sifatida kiritilgan; tashqi CDN kerak emas.
Jonli chiqarishdan oldin kompaniya 290 va ikkinchi kompaniya bilan filtr
variantlari, jadval va native filter RLS natijalarini haqiqiy serverda tekshiring.
