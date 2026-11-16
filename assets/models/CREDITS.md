# Модели и материалы

Что в игре сделано не нами, чьё это и на каких условиях взято. Всё остальное — город и берега, здания,
комнаты, сухогруз, автобус, мотоциклы и прочая мелкая техника, вывески, значки, звуки и музыка — создаётся
кодом проекта.

| Что | Автор и набор | Лицензия | Откуда взяты файлы |
|---|---|---|---|
| Люди: модели и текстуры (`chars/`) | **Elbolilloduro** — «Characters PSX» | см. примечание | репозиторий `Mesh2Motion/mesh2motion-app` (`static/assets/human/variations`) |
| Скелет и клипы анимации (`anims/`) | проект **Mesh2Motion** | CC0 | там же (`static/assets/human/animations`) |
| Машины: 10 моделей (`veh/`) | **GGBot** — «PSX Style Cars» | CC0 | копия набора в репозитории `Raccoon-Formality/Parking_Ticket_Mayhem` |
| Такси (`veh/taxi`) | **MoiDev** — «Yellow Taxi/Cab - PS1 Car» | CC-BY-SA-4.0 | копия набора в репозитории `Langorithm/3d-models` (`yellow_taxicab_-_ps1_car`) |
| Автобус (`veh/bus`) | код проекта, `tools/gen_bus.py` | — | — |
| Мотоцикл-круизер (`veh/b_moto`) | **Duhgless** — «Another PSX Style Low-poly Bike» | CC0 | копия в репозитории `webbertakken/citymap` (`motorbike.glb`) |
| Велосипеды (`veh/b_cycle`, `veh/b_bmx`) | **Kenney** — «Starter Kit: Racing» / «Car Kit» | CC0 | `KenneyNL/Starter-Kit-Racing` |
| Скутеры, мопед, спортбайк, кросс, квадроцикл, карт, гольф-кар и детали коляски/трайка | код проекта, `game/bikes.py` | — | — |
| Панели интерфейса (`assets/tex/ui_panel.png`, `ui_row.png`) | **rohhsa** — «FREEPSXUI» | CC0 | копия в репозитории `Balwanek-ola/haven-2026` (`FREEPSXUI`) |
| Мебель и техника в комнатах: 74 предмета (`furn/`) | **Elbolilloduro** — «Pack of low poly psx style models» | см. примечание | сборник `M3-org/retro3d-assets` (папка `Furniture`) |
| Пистолет и пистолет с глушителем (`weapons/pistol`, `silenced`) | **Mextie** — «Low-Poly Glock Model»; глушитель добавлен кодом | см. примечание | сборник `M3-org/retro3d-assets` (`Weapons/low-poly-glock`) |
| Пистолет-пулемёт, гранатомёт, нож (`uzi`, `rocket`, `knife`) | **Ace Spectre** — «PS1 Heavy and Light Weapons Pack» | см. примечание | там же (`Weapons/Heavy Weapons Pack`) |
| Двустволка (`double`) | **Cemckrc** — «Double Barrel Shotgun Psx Style» | см. примечание | там же (`Weapons/DoubleBarrelShotgun`) |
| Карабин М4 (`m4`) | «Low-Poly M4A1» с OpenGameArt; имя автора в сборнике не указано | см. примечание | там же (`Weapons/M4A1`) |
| Дробовик, автомат, снайперская винтовка (`shotgun`, `ak`, `sniper`) | набор из папки «You see Ivan Pack»; по списку сборника это, по-видимому, **ACE-X6** — «Modern Weapons (PS1 style)» | см. примечание | там же (`Weapons/Guns/You see Ivan Pack`) |
| Граната и бутылка с зажигательной смесью (`grenade`, `molotov`) | **Quaternius** — Toon Shooter Game Kit | CC0 | репозиторий `chibifire-stages/quaternius-stage` |
| Бита (`bat`) | **Quaternius** — Zombie Apocalypse Kit | CC0 | там же |
| Материалы города (`assets/tex`): стены, окна, двери, крыши, асфальт, плитка, трава, листва, кора, металл, дерево | **Craig Snedeker** — Classic64 Asset Library | CC0 | сборник `M3-org/retro3d-assets` (папки `*/Materials`) |
| Материалы комнат (`assets/tex/int_*`): полы, обои, панели, картины, книги, товары на полках, инструменты, бумаги | **Craig Snedeker** — Classic64 Asset Library | CC0 | там же |

Страницы авторов:

- Elbolilloduro — <https://elbolilloduro.itch.io/characters-psx> (люди),
  <https://elbolilloduro.itch.io/paquete-de-modelos-low-poly-estilo-psx-2> (мебель)
- Mesh2Motion — <https://github.com/Mesh2Motion/mesh2motion-app>
- GGBot (GGBotNet) — <https://ggbot.itch.io/psx-style-cars>
- MoiDev — <https://sketchfab.com/3d-models/yellow-taxicab-ps1-car-c07a0f442a6b482797c523c91a453395> (CC-BY-SA-4.0: <https://creativecommons.org/licenses/by-sa/4.0/>)
- Duhgless — <https://duhgless.itch.io/another-psx-style-low-poly-bike>
- rohhsa — <https://rohhsa.itch.io/free-psx-ui>
- Kenney — <https://kenney.nl>
- Craig Snedeker — <https://craigsnedeker.itch.io/classic64-asset-library>
- Quaternius — <https://quaternius.com>
- Mextie — <https://mextie.itch.io/low-poly-glock>
- Ace Spectre — <https://ace-spectre.itch.io/ps1-heavy-and-light-weapons-pack>
- Cemckrc — <https://cemckrc.itch.io/double-barrel-shotgun-psx-ps1-style>
- «Low-Poly M4A1» — <https://opengameart.org/content/low-poly-m4a1>
- ACE-X6 — <https://ace-x6.itch.io/modern-weapons-ps1-style>
- сборник — <https://github.com/M3-org/retro3d-assets>

CC0 1.0 — общественное достояние: можно использовать, изменять и распространять без условий
(<https://creativecommons.org/publicdomain/zero/1.0/>). Авторов мы всё равно называем — спасибо им.

## Примечание о персонажах

В репозитории Mesh2Motion все модели объявлены CC0 (файл `LICENSE-CC0.MD`), а автором этих назван
Elbolilloduro (`src/lib/RigConfig.ts`).
На странице самого набора автор формулирует условия иначе: набор бесплатен для любых проектов, в том числе
коммерческих, указывать авторство не обязательно, но **перевыкладывать набор, даже изменённый, нельзя**.

В игре модели лежат в собранном виде (`.bam`, один общий скелет, упрощённая привязка) как часть игры, а не
как набор для скачивания. Если вам нужны сами модели — берите их у автора по ссылке выше, а не отсюда.
Если автор попросит убрать модели из проекта, их нужно будет заменить: таблицы соответствия лежат в
`game/models.py`, импорт — в `tools/import_psx.py`.

## Примечание о мебели

Мебель взята из сборника `M3-org/retro3d-assets`. О нём самом сказано: модели можно использовать в том числе
в коммерческих проектах, без указания авторства и без условия «распространять на тех же условиях»; набор
мебели назван там со ссылкой на страницу автора. Саму страницу автора мы открыть не смогли и условия на ней
не сверяли. Автор тот же, что у персонажей, поэтому действуем так же: модели лежат в собранном виде как
часть игры (`furn.bam`: предметы склеены из частей, текстуры уменьшены), а не как набор для скачивания;
исходный набор берите у автора. Если автор попросит убрать мебель, её нужно будет заменить: список предметов —
в `tools/import_furniture.py`, расстановка по комнатам — в `game/interiors.py`.

## Примечание об оружии

Одиннадцать моделей оружия взяты из сборника `M3-org/retro3d-assets` (папка `Weapons`). О сборнике сказано:
всё в нём можно использовать в том числе в коммерческих проектах, без указания авторства и без условия
«распространять на тех же условиях». Наборы названы в его описании со ссылками на страницы авторов; сами
страницы мы открыть не смогли и условия на них не сверяли. Две оговорки:

- у карабина М4 в описании сборника есть только ссылка на OpenGameArt, без имени автора; на OpenGameArt
  у каждой работы своя лицензия, и какую выбрал автор, мы не проверяли;
- папка с дробовиком, автоматом и винтовкой называется «You see Ivan Pack», а в списке сборника такого
  названия нет; ближе всего по составу набор «Modern Weapons (PS1 style)» автора ACE-X6, но это догадка.

Если кто-то из авторов попросит убрать модель, её нужно будет заменить: таблица моделей — в
`tools/import_weapons.py`, соответствие оружию игры — в `game/models.py`. Бита, граната и бутылка остались
от Quaternius; их импорт — `tools/import_models.py weapons`.

## Примечание о мотоциклах и велосипедах

Круизер `b_moto` (используется для «Ворона», «Странника», патрульного мотоцикла, трайка и «Тайги» с коляской)
импортирован из CC0-набора **Duhgless** «Another PSX Style Low-poly Bike» с отделением поворотной вилки и
колёс в `tools/import_vehicles.py`, а велосипеды `b_cycle` и `b_bmx` — из CC0-набора Kenney. Остальные виды
(спортивный и кроссовый мотоциклы, скутеры, мопед, квадроцикл, грузовой мотороллер, карт и гольф-кар)
собирает код (`game/bikes.py`) — из колёс, труб и обтекаемых деталей, подогнанных под посадку ездока.

## Шрифты

Inter, Oswald, Caveat, Russo One и Dela Gothic One распространяются по SIL Open Font License; тексты лицензии
лежат рядом со шрифтами в `assets/fonts`. Inter и Oswald — интерфейс, Caveat — рукописные названия заданий,
Russo One и Dela Gothic One — вывески и заставка.

## Примечание о материалах города и комнат

В описании сборника `M3-org/retro3d-assets` библиотека Classic64 названа как его часть, а папки с материалами
(`Bricks/Materials`, `Windows/Materials`, `Floor/Materials` и другие) повторяют её устройство; пофайлово мы это
не сверяли. Сам автор библиотеки отмечает, что часть её файлов переработана из работ других авторов. Надпись
судоходной компании с борта морского контейнера мы убрали; товары на фотографиях витрин и полок сняты так
мелко, что названия на них не читаются. Обои, плакаты, вывески и стенды в комнатах нарисованы кодом
(`tools/gen_interior.py`).

## Что делает импорт

- `tools/import_psx.py` приводит всех людей к одному скелету (клипы анимации общие для всех) и упрощает
  привязку к костям. У машин он отделяет колёса и, сравнивая варианты окраски из набора, находит на текстуре
  окрашенные места кузова — так машину можно перекрашивать.
- Из 13 исходных моделей людей получается 41 облик: 11 моделей как есть, 12 сборных (тело одной модели, голова
  другой) и 18 вариантов с перекрашенной одеждой. Кисти рук перепривязаны к костям: в исходнике кисть-«варежка»
  была привязана к костям отдельных пальцев и в движении рвалась веером. Песочные штаны одной из моделей
  перекрашены в тёмные: издали они сливались с кожей.
- `tools/import_furniture.py` собирает мебель: склеивает соприкасающиеся части в один предмет, ставит его на пол
  и уменьшает текстуры. `tools/gen_interior.py` готовит текстуры комнат из материалов Classic64.
- `tools/gen_city.py` собирает из материалов текстуры фасадов и первых этажей: кладёт на стену окна и двери,
  добавляет потёки и тени, рисует разметку дорог и ночные окна.
- `tools/import_weapons.py` читает модели оружия из `.blend` и `.glb`, поворачивает их стволом вперёд, приводит
  к настоящей длине и ставит начало координат туда, где рукоять лежит в ладони; текстуры уменьшает.
  `tools/import_models.py weapons` делает то же для биты, гранаты и бутылки.
