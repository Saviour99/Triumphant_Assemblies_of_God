# Page banner photos

All files: 1600x900 (16:9) JPEG, progressive, metadata stripped, each <= 250 KB,
plus a `.webp` twin of the same crop. All are stock photos from Unsplash under the
[Unsplash License](https://unsplash.com/license) (free for commercial use, no
attribution required — credit given here as courtesy). None of the existing
photos in `app/static/img/` were reused (see note at the bottom). None duplicate
the homepage hero video/poster (`app/static/img/hero-poster.jpg`, `app/static/video/hero.mp4`).

Every image was opened and visually checked before acceptance. Every image that
shows people shows Black people only.

| page | file | subject shown | source URL | photographer | license | visually verified | focal point hint |
|---|---|---|---|---|---|---|---|
| about | `pages/about.jpg` | Packed congregation in a church hall, hands raised | https://unsplash.com/photos/_SIrxHGnqVY | Ufoma Ojo | Unsplash License | yes. Nigerian/West African congregation (all Black men and women), woman in yellow with glasses at centre | centre-weighted crowd. `object-position: 50% 40%` |
| ministries | `pages/ministries.jpg` | Robed church choir singing from hymnals, director in foreground right | https://unsplash.com/photos/8__esxuic9Q | John Onaeko | Unsplash License | yes. Choir at Scripture Pasture Christian Center, Ibadan, Nigeria. All Black singers and director | choir across the middle, director on the right. `object-position: 45% 50%` |
| sermons | `pages/sermons.jpg` | Preacher in white shirt and red tie, preaching with a mic beside a glass pulpit | https://unsplash.com/photos/48x1teBWvys | JClick Photgraph | Unsplash License | yes. A single Black male preacher against a dark blue backdrop | face upper-centre-right, dark empty left side for text. `object-position: 60% 30%` |
| events | `pages/events.jpg` | Worship team in Nigerian attire (gele, coral beads, agbada) singing at mics on stage | https://unsplash.com/photos/7cJqMv5uOOI | Junior Gabriel | Unsplash License | yes. All Black men and women on stage | faces in the top third, man on the right. `object-position: 60% 20%` |
| blog | `pages/blog.jpg` | Open Bible on a wooden table with a candle, a glass of wine, bread and an ivy plant | https://unsplash.com/photos/ZghUd3xkxM4 | Emily Whitten | Unsplash License | yes. No people | Bible lower-centre-left, candle on the left. `object-position: 40% 60%` |
| devotionals | `pages/devotionals.jpg` | Young man reading a Bible in a dark church under a glowing red neon cross | https://unsplash.com/photos/de4rRBVOMPc | Gift Habeshaw | Unsplash License | yes. One Black (Ethiopian) man, Addis Ababa. T-shirt text cropped out | figure centre-right, cross at top centre, dark sides. `object-position: 55% 35%` |
| ebooks | `pages/ebooks.jpg` | Young man in a plaid shirt reading a paperback at a desk | https://unsplash.com/photos/RS3Rj5QvVgQ | Emmanuel Ikwuegbu | Unsplash License | yes. One Black young man, Nigeria | face centre-right, book lower-left. `object-position: 60% 35%` |
| testimonies | `pages/testimonies.jpg` | Young women singing and rejoicing in worship, beaming smiles, hands raised | https://unsplash.com/photos/MsVfcHU9d_c | Adeyemi Emmanuel Abebayo | Unsplash License | yes. True Worshippers Church, Ogbomoso, Nigeria. All Black young women and men | faces in the upper half, left and centre-right. `object-position: 55% 25%` |
| search | `pages/search.jpg` | Open Bible lying on a weathered teal wooden table, blurred wood behind | https://unsplash.com/photos/ww4zVgcOdJY | Aaron Burden | Unsplash License | yes. No people | Bible lower-centre, calm upper area for text. `object-position: 50% 60%` |
| contact | `pages/contact.jpg` | Bright blue church building with a cross and two arched doors, under a dramatic sky | https://unsplash.com/photos/-z-zmOjmR-I | Rohan Reddy | Unsplash License | yes. No people. Church in Tabora, Tanzania | church centred, sky in the top half. `object-position: 50% 55%` |
| giving | `pages/giving.jpg` | Wooden church offering box with an inlaid cross and offering envelopes | https://unsplash.com/photos/L7kHt5x_Slc | Leiada Krözjhen | Unsplash License | yes. No people | box centre-left. `object-position: 40% 50%` |
| payment | `pages/payment.jpg` | Woman with braids, eyes closed, hands pressed together in thankful prayer | https://unsplash.com/photos/rAH3UcA3ruU | Jametlene Reskp | Unsplash License | yes. One Black woman | face and hands centre-right, dark wall on the left for text. `object-position: 60% 40%` |
| legal | `pages/legal.jpg` | Quiet, dim church interior: wooden pews and stone columns with a shaft of sunlight | https://unsplash.com/photos/hX1gt56nj4U | Sandie Clarke | Unsplash License | yes. No people | low-contrast, even. `object-position: 50% 50%` |
| members | `pages/members.jpg` | Two young women embracing, cheek to cheek, laughing | https://unsplash.com/photos/KsfSu6kwBDU | Alexandre Juca | Unsplash License | yes. Two Black women, Luanda, Angola | faces fill the centre and right, upper half. `object-position: 55% 30%` |
| prayer | `pages/prayer.jpg` | Women in gele headwraps praying with eyes closed and palms open in a church | https://unsplash.com/photos/vfmd4bVRvCs | Prince Kwembe | Unsplash License | yes. All Black women in African prints. Wall banners with text cropped out | main face upper-centre. `object-position: 50% 30%` |

Short Unsplash URLs (`/photos/<id>`) redirect to the full photo page.

## Existing `app/static/img` photos, not reused

`prayer_service.jpg` / `prayer_service_web.jpg`, `sunday_service.jpg` / `sunday_service_web.jpg`,
`youth.jpg` / `youth_web.jpg` and `youth_service.jpg` / `youth_service_web.jpg` all show
non-Black (white / Latino / East Asian-appearing) congregations, so under the owner's rule they
should not be used for people imagery. The remaining photos (pastor and deacon portraits) are
portraits of the church's own leaders. They are not banner material.
