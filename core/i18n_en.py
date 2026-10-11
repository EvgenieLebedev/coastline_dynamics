# -*- coding: utf-8 -*-
"""Английские строки интерфейса: русская строка из кода -> перевод.

Ключ должен совпадать со строкой в вызове tr() знак в знак, подстановки (%s, %d, %.1f)
в переводе идут в том же порядке. Полноту словаря проверяет Скрипты/проверка_перевода.py.
"""

EN = {
    # --------------------------------------------------- plugin.py
    "&Динамика береговой линии": "&Coastline Dynamics",
    "Полный расчёт (шаги 1–5)…": "Full run (steps 1–5)…",
    "1. Загрузка снимков из каталога STAC…": "1. Download scenes from the STAC catalogue…",
    "2. Годовые композиты водного индекса…": "2. Annual composites of the water index…",
    "2а. Водный индекс по готовым годовым растрам…": "2a. Water index from ready-made annual rasters…",
    "3. Годовые береговые линии…": "3. Annual shorelines…",
    "4. Темпы смещения берега…": "4. Rates of shoreline change…",
    "5. Обобщённые темпы по участкам берега…": "5. Summarised rates along the coast…",
    "Динамика береговой линии": "Coastline Dynamics",
    "График смещения берега в точке": "Shoreline change chart for a point",
    "Справка": "Help",
    ("Не включён модуль «Processing» (Анализ данных). Включите его в диалоге «Модули — Управление "
     "модулями» и повторите."):
        ("The Processing plugin is not enabled. Enable it in “Plugins – Manage and Install Plugins” "
         "and try again."),
    # ------------------------------------------------- provider.py
    "Динамика береговой линии: годовые береговые линии и темпы их смещения по спутниковым снимкам":
        "Coastline Dynamics: annual shorelines and rates of their change from satellite imagery",
    # -------------------------------------------------- styling.py
    "отступание быстрее 5 м/год": "retreat faster than 5 m/yr",
    "отступание 2–5 м/год": "retreat 2–5 m/yr",
    "отступание 1–2 м/год": "retreat 1–2 m/yr",
    "отступание 0,3–1 м/год": "retreat 0.3–1 m/yr",
    "устойчиво (менее 0,3 м/год)": "stable (less than 0.3 m/yr)",
    "нарастание 0,3–1 м/год": "growth 0.3–1 m/yr",
    "нарастание 1–2 м/год": "growth 1–2 m/yr",
    "нарастание 2–5 м/год": "growth 2–5 m/yr",
    "нарастание быстрее 5 м/год": "growth faster than 5 m/yr",
    "Идентификатор": "Identifier",
    "Год": "Year",
    "Надёжность": "Certainty",
    "Длина, м": "Length, m",
    "Индекс": "Index",
    "Порог индекса": "Index threshold",
    "Темп, м/год": "Rate, m/yr",
    "Значимость (p)": "Significance (p)",
    "Ст. ошибка темпа, м/год": "Std. error of the rate, m/yr",
    "Годы вне расчёта": "Years excluded",
    "Направление смещения, °": "Direction of movement, °",
    "Разброс направлений, °": "Spread of directions, °",
    "Лет в расчёте": "Years used",
    "Охват, лет": "Span, years",
    "Размах положений, м": "Range of positions, m",
    "Итоговое смещение, м": "Net movement, m",
    "Год наибольшего выдвижения": "Year of the most seaward position",
    "Год наибольшего отступания": "Year of the most landward position",
    "Радиус обобщения, м": "Summary radius, m",
    "Точек в круге": "Points in the circle",
    "%s г., м": "%s, m",
    "море": "sea",
    "прибрежная полоса": "coastal strip",
    "суша и внутренние воды": "land and inland waters",
    # ----------------------------------------------- chart_dock.py
    "надёжно": "good",
    "опорный год выпадает из ряда": "the baseline year is an outlier",
    "линии разных лет не ложатся на одно направление":
        "shorelines of different years do not lie along one direction",
    "мало лет с данными": "too few years with data",
    "мало точек в круге обобщения": "too few points in the summary circle",
    "Включите инструмент и щёлкните по точке слоя темпов смещения берега":
        "Turn the tool on and click a point of the rates layer",
    "Положение, м   (+ к морю)": "Position, m   (+ seaward)",
    "Темп не определён: в точке недостаточно лет с данными.":
        "The rate is undefined: too few years with data at this point.",
    "нарастает": "growing",
    "отступает": "retreating",
    "<b>Берег %s на %s м/год</b>": "<b>The coast is %s at %s m/yr</b>",
    "; %s — тренд %s": "; %s, the trend is %s",
    "значим": "significant",
    "незначим": "not significant",
    "смещение за период %s м": "net movement %s m",
    "размах положений %.0f м": "range of positions %.0f m",
    "исключены годы: %s": "excluded years: %s",
    "надёжность: %s": "certainty: %s",
    "График смещения берега": "Shoreline change chart",
    "Выбрать точку на карте": "Pick a point on the map",
    "Сохранить график…": "Save chart…",
    "Точка не выбрана.": "No point selected.",
    "Рядом со щелчком нет точек слоя темпов. Слой должен быть видимым.":
        "No points of the rates layer near the click. The layer must be visible.",
    "Сохранить график": "Save chart",
    "Изображение PNG (*.png)": "PNG image (*.png)",
    # ----------------------------------------------- algorithms.py
    "Как в DEA Coastlines (отклонение пары «год — расстояние»)":
        "As in DEA Coastlines (deviation of the “year – distance” pair)",
    "По остаткам тренда (прямая Тейла — Сена)": "By trend residuals (Theil–Sen line)",
    "Не исключать": "Do not exclude",
    ("<p>Методика: Bishop-Taylor R. et al. Mapping Australia's dynamic coastline at mean sea level "
     "using three decades of Landsat imagery // Remote Sensing of Environment. 2021. Vol. 267. "
     "112734.</p>"):
        ("<p>Method: Bishop-Taylor R. et al. (2021). Mapping Australia's dynamic coastline at mean sea "
         "level using three decades of Landsat imagery. Remote Sensing of Environment, 267, 112734.</p>"),
    "Расчёт остановлен пользователем.": "The run was stopped by the user.",
    "1. Загрузка снимков из каталога STAC": "1. Download scenes from the STAC catalogue",
    ("<p>Находит в каталоге Microsoft Planetary Computer все сцены Landsat или Sentinel-2 на участок "
     "за заданные годы и месяцы и сохраняет вырезки по участку в локальный архив. Сцены целиком не "
     "скачиваются: по сети читаются только нужные фрагменты.</p><p>В архив попадают три канала "
     "отражения (зелёный, ближний ИК, средний ИК); облака, тени и снег замаскированы. На каждый день "
     "съёмки создаётся один файл; сведения о сценах записываются в таблицу "
     "<i>scenes.csv</i>.</p><p><b>Повторный запуск с той же папкой докачивает недостающее</b>: уже "
     "загруженные сцены пропускаются, поэтому ряд можно продлевать год за годом.</p><p><b>Месяцы.</b> "
     "Для замерзающих морей следует ограничиться безлёдным сезоном (например, с апреля по октябрь): "
     "лёд и снег искажают водный индекс.</p><p>Регистрация в каталоге не требуется, нужен доступ в "
     "интернет.</p>"):
        ("<p>Finds all Landsat or Sentinel-2 scenes over the area for the given years and months in "
         "the Microsoft Planetary Computer catalogue and saves clips of the area to a local archive. "
         "Whole scenes are not downloaded: only the required fragments are read over the "
         "network.</p><p>The archive holds three reflectance bands (green, near infrared, shortwave "
         "infrared); clouds, shadows and snow are masked. One file is created per acquisition day; "
         "scene details are written to the <i>scenes.csv</i> table.</p><p><b>A repeated run with the "
         "same folder fetches only what is missing</b>: scenes already downloaded are skipped, so the "
         "series can be extended year by year.</p><p><b>Months.</b> For seas that freeze, keep to the "
         "ice-free season (for example, April to October): ice and snow distort the water "
         "index.</p><p>No account in the catalogue is needed; internet access is required.</p>"),
    "Участок (охват)": "Area (extent)",
    "Съёмочная система": "Sensor",
    "Первый год": "First year",
    "Последний год": "Last year",
    "Первый месяц сезона": "First month of the season",
    "Последний месяц сезона": "Last month of the season",
    "Наибольшая облачность сцены по каталогу, %": "Maximum scene cloud cover in the catalogue, %",
    "Наименьшая доля ясных пикселей на участке, %": "Minimum share of clear pixels over the area, %",
    "Приборы Landsat": "Landsat instruments",
    "Только сцены высшей категории геометрической точности (Tier 1)":
        "Only scenes of the highest geometric accuracy category (Tier 1)",
    "Очистка маски облаков: замыкание, размыкание, расширение, м":
        "Cloud mask clean-up: closing, opening, dilation, m",
    "Число одновременных загрузок": "Number of simultaneous downloads",
    "Система координат архива (по умолчанию — зона UTM участка)":
        "Archive coordinate system (default: the UTM zone of the area)",
    "Папка архива сцен": "Scene archive folder",
    "Число загруженных наблюдений": "Number of downloaded observations",
    "Не задан участок.": "No area given.",
    "Первый месяц сезона должен быть не позже последнего.":
        "The first month of the season must not be later than the last.",
    "Очистка маски облаков задаётся тремя числами через запятую, например 60,300,150.":
        "The cloud mask clean-up is given as three comma-separated numbers, for example 60,300,150.",
    "Система координат архива должна быть прямоугольной (в метрах) и иметь код EPSG.":
        "The archive coordinate system must be projected (in metres) and have an EPSG code.",
    "Всего пригодных наблюдений в архиве: %d.": "Usable observations in the archive: %d.",
    "2. Годовые композиты водного индекса": "2. Annual composites of the water index",
    ("<p>По каждой сцене архива вычисляет водный индекс, затем для каждого года находит попиксельную "
     "<b>медиану</b> индекса, его стандартное отклонение и число наблюдений. Медиана за год подавляет "
     "случайные помехи отдельных снимков: остатки облаков, волнение, сгонно-нагонные колебания "
     "уровня.</p><p>Для лет с малым числом снимков дополнительно строится <b>трёхлетний композит</b> "
     "(по году и двум соседним): им на следующем шаге заменяются пиксели, где наблюдений меньше "
     "шести.</p><p><b>Отбор по уровню моря</b> (необязательно). В приливных морях положение уреза "
     "зависит от фазы прилива. Если задать таблицу уровня (CSV: дата и время UTC; уровень), в расчёт "
     "войдут только снимки, сделанные при уровне, близком к среднему: по умолчанию — средняя половина "
     "размаха, как в DEA Coastlines. Для бесприливных морей со сгонами и нагонами вместо уровня можно "
     "подать ветровой показатель и выбрать в дополнительных параметрах отбор по доле "
     "наблюдений.</p><p>Результат — папка с файлами <i>mndwi_ГГГГ.tif</i> (каналы: индекс, стандартное "
     "отклонение, число наблюдений), <i>mndwi_ГГГГ_gapfill.tif</i> и <i>rgb_ГГГГ.tif</i> (цветосинтез "
     "для просмотра).</p>"):
        ("<p>Computes the water index for every scene in the archive, then for every year finds the "
         "per-pixel <b>median</b> of the index, its standard deviation and the number of observations. "
         "The annual median suppresses random noise in individual images: cloud remnants, waves, "
         "wind-driven changes in water level.</p><p>For years with few images a <b>three-year "
         "composite</b> is also built (from the year and its two neighbours): at the next step it "
         "replaces pixels with fewer than six observations.</p><p><b>Selection by sea level</b> "
         "(optional). In tidal seas the position of the waterline depends on the tide. If a sea level "
         "table is given (CSV: UTC date and time; level), only images taken at a level close to the "
         "mean are used: by default the middle half of the range, as in DEA Coastlines. For non-tidal "
         "seas with wind surges you can supply a wind indicator instead of the level and choose "
         "selection by share of observations in the advanced parameters.</p><p>The result is a folder "
         "with the files <i>mndwi_YYYY.tif</i> (bands: index, standard deviation, number of "
         "observations), <i>mndwi_YYYY_gapfill.tif</i> and <i>rgb_YYYY.tif</i> (colour composite for "
         "viewing).</p>"),
    "Папка архива сцен (результат шага 1)": "Scene archive folder (result of step 1)",
    "Водный индекс": "Water index",
    "Первый год (пусто — с начала архива)": "First year (empty: from the start of the archive)",
    "Последний год (пусто — до конца архива)": "Last year (empty: to the end of the archive)",
    "Строить трёхлетние композиты": "Build three-year composites",
    "Сохранять цветосинтез для просмотра": "Save a colour composite for viewing",
    "Таблица уровня моря для отбора снимков (CSV)": "Sea level table for selecting scenes (CSV)",
    "Таблицы CSV (*.csv *.txt)": "CSV tables (*.csv *.txt)",
    "Правило отбора по уровню": "Rule for selection by level",
    "По размаху уровня (как в DEA Coastlines; для приливов)":
        "By the range of the level (as in DEA Coastlines; for tides)",
    "По доле наблюдений, ближайших к центру (для сгонов и нагонов)":
        "By the share of observations closest to the centre (for wind surges)",
    "Доля размаха (или доля наблюдений), остающаяся в расчёте":
        "Share of the range (or share of observations) kept in the analysis",
    "Центральный уровень (пусто — средний по ряду)": "Central level (empty: the mean of the series)",
    "Объём оперативной памяти на расчёт, МБ": "Memory for the calculation, MB",
    "Добавить в проект": "Add to the project",
    "Композиты последнего года": "Composites of the last year",
    "Композиты всех лет": "Composites of all years",
    "Ничего": "Nothing",
    "Папка композитов": "Composites folder",
    "Цветосинтез %d": "Colour composite %d",
    "2а. Водный индекс по готовым годовым растрам": "2a. Water index from ready-made annual rasters",
    ("<p>Замена шагов 1 и 2 для случая, когда годовые безоблачные композиты отражения уже есть (по "
     "одному многоканальному растру на год в общей сетке). Алгоритм вычисляет водный индекс и "
     "раскладывает файлы так, как их ожидает шаг 3.</p><p>Год берётся из имени файла. Номера каналов "
     "зелёного и инфракрасного диапазонов зависят от состава растра: для шести каналов Landsat в "
     "порядке «синий, зелёный, красный, ближний ИК, средний ИК 1, средний ИК 2» это 2 и 5 (MNDWI) либо "
     "2 и 4 (NDWI).</p><p><b>Ограничение.</b> По готовой медиане нельзя восстановить число наблюдений "
     "и разброс индекса, поэтому проверки надёжности («мало наблюдений», «неустойчивый индекс») на "
     "таких данных не срабатывают.</p>"):
        ("<p>Replaces steps 1 and 2 when annual cloud-free reflectance composites already exist (one "
         "multi-band raster per year on a common grid). The algorithm computes the water index and "
         "arranges the files the way step 3 expects them.</p><p>The year is taken from the file name. "
         "The numbers of the green and infrared bands depend on the raster: for six Landsat bands in "
         "the order “blue, green, red, near infrared, shortwave infrared 1, shortwave infrared 2” they "
         "are 2 and 5 (MNDWI) or 2 and 4 (NDWI).</p><p><b>Limitation.</b> The number of observations "
         "and the spread of the index cannot be recovered from a ready-made median, so the certainty "
         "checks (“few observations”, “unstable index”) do not work on such data.</p>"),
    "Годовые растры отражения": "Annual reflectance rasters",
    "Шаблон года в имени файла (регулярное выражение)":
        "Year pattern in the file name (regular expression)",
    "Номер зелёного канала": "Number of the green band",
    "Номер инфракрасного канала": "Number of the infrared band",
    "Множитель перевода значений в отражение": "Multiplier converting values to reflectance",
    "Название индекса": "Index name",
    "В имени файла не найден год, растр пропущен: %s":
        "No year found in the file name, raster skipped: %s",
    "3. Годовые береговые линии": "3. Annual shorelines",
    ("<p>Проводит береговую линию каждого года как изолинию водного индекса на уровне порога. "
     "Положение линии между центрами пикселей находится интерполяцией, поэтому точность выше размера "
     "пикселя.</p><p>Перед этим данные очищаются:</p><ul><li>пиксели, где за год меньше шести "
     "наблюдений, заменяются трёхлетним композитом;</li><li>пятна «суши», не подтверждённые соседними "
     "годами, отбрасываются;</li><li>остаётся только вода, связанная с морем: озёра, пруды и узкие "
     "водотоки внутри суши в расчёт не попадают;</li><li>расчёт ограничен прибрежной полосой заданной "
     "ширины.</li></ul><p><b>Море</b> по умолчанию — крупнейший постоянный водоём участка. Если на "
     "участке есть сопоставимая по размеру лагуна или лиман, укажите слой с точкой или полигоном в "
     "море. Для внутренних водоёмов (озёра, водохранилища, пруды) выберите вариант «все водоёмы» и "
     "отключите в дополнительных параметрах исключение узких водотоков.</p><p>Поле <i>certainty</i> "
     "отмечает участки линий пониженной надёжности: <i>insufficient data</i> — меньше пяти наблюдений, "
     "<i>unstable data</i> — стандартное отклонение индекса больше 0,3.</p>"):
        ("<p>Draws the shoreline of every year as a contour of the water index at the threshold level. "
         "The position of the line between pixel centres is found by interpolation, so the precision "
         "is finer than the pixel size.</p><p>The data are cleaned first:</p><ul><li>pixels with fewer "
         "than six observations in the year are replaced with the three-year "
         "composite;</li><li>patches of “land” not confirmed by neighbouring years are "
         "discarded;</li><li>only water connected to the sea is kept: lakes, ponds and narrow inland "
         "watercourses are left out;</li><li>the analysis is restricted to a coastal strip of the "
         "given width.</li></ul><p><b>The sea</b> is by default the largest permanent water body in "
         "the area. If the area contains a lagoon or estuary of comparable size, give a layer with a "
         "point or polygon in the sea. For inland water bodies (lakes, reservoirs, ponds) choose the "
         "“all water bodies” option and turn off the exclusion of narrow watercourses in the advanced "
         "parameters.</p><p>The <i>certainty</i> field marks parts of the lines with lower certainty: "
         "<i>insufficient data</i> means fewer than five observations, <i>unstable data</i> means the "
         "standard deviation of the index is above 0.3.</p>"),
    "Папка композитов (результат шага 2)": "Composites folder (result of step 2)",
    "Порог индекса (вода — выше порога)": "Index threshold (water is above the threshold)",
    "Первый год (пусто — все)": "First year (empty: all)",
    "Последний год (пусто — все)": "Last year (empty: all)",
    "Ширина прибрежной полосы в каждую сторону, м": "Width of the coastal strip on each side, m",
    "Что считать морем": "What counts as the sea",
    "Крупнейший постоянный водоём участка": "The largest permanent water body in the area",
    "Все водоёмы шире 300 м (лагуны, лиманы, озёра, пруды)":
        "All water bodies wider than 300 m (lagoons, estuaries, lakes, ponds)",
    "Слой морской акватории: точки или полигоны в море": "Sea layer: points or polygons in the sea",
    "Исключаемые участки (полигоны)": "Excluded areas (polygons)",
    "Отбрасывать «сушу», не подтверждённую соседними годами":
        "Discard “land” not confirmed by neighbouring years",
    "Исключать узкие водотоки внутри суши": "Exclude narrow inland watercourses",
    "Наименьшее число вершин линии": "Minimum number of line vertices",
    "Стандартное отклонение индекса, выше которого данные неустойчивы":
        "Standard deviation of the index above which the data are unstable",
    "Число наблюдений, ниже которого данных недостаточно":
        "Number of observations below which the data are insufficient",
    "Годовые береговые линии": "Annual shorelines",
    "Маска прибрежной полосы": "Coastal strip mask",
    "Повторяемость суши": "Land frequency",
    ("Береговая линия не выделена ни за один год. Проверьте порог индекса и то, что участок включает и "
     "море, и сушу."):
        ("No shoreline was extracted for any year. Check the index threshold and that the area "
         "includes both sea and land."),
    "В слое береговых линий нет поля года «%s».": "The shoreline layer has no year field “%s”.",
    "Слой береговых линий пуст.": "The shoreline layer is empty.",
    "4. Темпы смещения берега": "4. Rates of shoreline change",
    ("<p>Вдоль береговой линии опорного года (по умолчанию — последнего) через равный шаг "
     "расставляются точки. Для каждой точки измеряется расстояние до береговой линии каждого года: "
     "положительное, если линия лежала мористее опорной, отрицательное — если ближе к суше. "
     "Направление определяется по значениям индекса в композитах.</p><p>По ряду расстояний строится "
     "линейная регрессия. Её наклон — средний темп, м/год (<i>rate_time</i>): <b>отрицательный — берег "
     "отступает, положительный — нарастает</b>. Годы с резко выпадающим положением линии "
     "предварительно исключаются.</p><p>Основные поля: <i>sig_time</i> — значимость тренда (p); "
     "<i>se_time</i> — стандартная ошибка темпа; <i>dist_ГГГГ</i> — положение линии года относительно "
     "опорной, м; <i>nsm</i> — смещение между первым и последним годом; <i>sce</i> — размах положений; "
     "<i>certainty</i> — надёжность (<i>good</i> либо причина сомнения).</p><p>Доверять следует "
     "точкам, где одновременно <i>certainty = good</i> и <i>sig_time</i> не больше 0,01: на карте они "
     "показаны крупными знаками.</p>"):
        ("<p>Points are placed at equal intervals along the shoreline of the baseline year (the last "
         "one by default). For every point the distance to the shoreline of each year is measured: "
         "positive if the line lay seaward of the baseline, negative if it lay landward. The direction "
         "is determined from the index values in the composites.</p><p>A linear regression is fitted "
         "to the series of distances. Its slope is the mean rate, m/yr (<i>rate_time</i>): <b>negative "
         "means the coast is retreating, positive means it is growing</b>. Years in which the line "
         "position is a strong outlier are excluded beforehand.</p><p>Main fields: <i>sig_time</i> is "
         "the significance of the trend (p); <i>se_time</i> is the standard error of the rate; "
         "<i>dist_YYYY</i> is the position of the year's line relative to the baseline, m; <i>nsm</i> "
         "is the movement between the first and the last year; <i>sce</i> is the range of positions; "
         "<i>certainty</i> is the certainty flag (<i>good</i> or the reason for doubt).</p><p>Trust "
         "the points where both <i>certainty = good</i> and <i>sig_time</i> is 0.01 or less: on the "
         "map they are shown with large symbols.</p>"),
    "Годовые береговые линии (результат шага 3)": "Annual shorelines (result of step 3)",
    "Поле года": "Year field",
    "Опорный год (пусто — последний)": "Baseline year (empty: the last one)",
    "Шаг точек вдоль берега, м": "Point spacing along the coast, m",
    "Наибольшее допустимое расстояние до линии года, м":
        "Maximum allowed distance to the year's shoreline, m",
    "Исключение выпадающих лет": "Exclusion of outlier years",
    "Темпы смещения берега": "Rates of shoreline change",
    "Береговые линии и композиты совпадают меньше чем по трём годам.":
        "Shorelines and composites share fewer than three years.",
    "5. Обобщённые темпы по участкам берега": "5. Summarised rates along the coast",
    ("<p>Сводит точечные темпы к обзорной картине. Вдоль береговой линии опорного года через половину "
     "радиуса ставятся обобщённые точки; для каждой берётся медиана годовых положений всех надёжных "
     "точек в круге заданного радиуса и по ней заново строится регрессия.</p><p>Слой удобен для мелких "
     "масштабов и для сравнения участков берега между собой. Точки, в круг которых попало слишком мало "
     "исходных точек, помечаются как <i>insufficient points</i>.</p>"):
        ("<p>Reduces point rates to an overview picture. Summary points are placed along the shoreline "
         "of the baseline year at intervals of half the radius; for each one the median of the annual "
         "positions of all reliable points within a circle of the given radius is taken and the "
         "regression is fitted again.</p><p>The layer is convenient for small scales and for comparing "
         "stretches of coast with each other. Points whose circle contains too few source points are "
         "flagged as <i>insufficient points</i>.</p>"),
    "Темпы смещения берега (результат шага 4)": "Rates of shoreline change (result of step 4)",
    "Обобщённые темпы": "Summarised rates",
    "Слой точек не похож на результат шага 4: нет полей dist_ГГГГ и certainty.":
        ("The point layer does not look like the result of step 4: the dist_YYYY and certainty fields "
         "are missing."),
    "Слой точек должен быть в прямоугольной системе координат с кодом EPSG.":
        "The point layer must be in a projected coordinate system with an EPSG code.",
    "Опорный год: %d.": "Baseline year: %d.",
    "В слое береговых линий нет линии опорного года %d.":
        "The shoreline layer has no line for the baseline year %d.",
    "Полный расчёт (шаги 1–5)": "Full run (steps 1–5)",
    ("<p>Выполняет всю цепочку за один запуск: загрузка снимков, годовые композиты, береговые линии, "
     "темпы смещения и обобщённые темпы. В рабочей папке создаются подпапки <i>scenes</i> и "
     "<i>composites</i> и файлы <i>shorelines.gpkg</i>, <i>rates.gpkg</i>, <i>hotspots.gpkg</i>; "
     "итоговые слои добавляются в проект.</p><p>Параметры, которых здесь нет, берутся по умолчанию. "
     "Для тонкой настройки выполняйте шаги по отдельности: каждый принимает на вход результат "
     "предыдущего.</p><p>Повторный запуск с той же рабочей папкой не скачивает снимки заново.</p>"):
        ("<p>Runs the whole chain in one go: scene download, annual composites, shorelines, rates of "
         "change and summarised rates. The working folder receives the subfolders <i>scenes</i> and "
         "<i>composites</i> and the files <i>shorelines.gpkg</i>, <i>rates.gpkg</i> and "
         "<i>hotspots.gpkg</i>; the result layers are added to the project.</p><p>Parameters that are "
         "not shown here take their default values. For fine tuning run the steps one by one: each "
         "takes the result of the previous one as input.</p><p>A repeated run with the same working "
         "folder does not download the imagery again.</p>"),
    "Рабочая папка": "Working folder",
    "Береговые линии": "Shorelines",
    "Темпы": "Rates",
    "=== Шаг %d из 5 ===": "=== Step %d of 5 ===",
    # --------------------------------------------- core/sensors.py
    "Landsat 4–9, Collection 2 Level-2 (30 м, с 1982 г.)":
        "Landsat 4–9, Collection 2 Level-2 (30 m, from 1982)",
    "Sentinel-2 L2A (10 м, с 2015 г.)": "Sentinel-2 L2A (10 m, from 2015)",
    # ------------------------------------------------ core/stac.py
    "Нет ответа от %s: %s": "No response from %s: %s",
    "Не удалось прочитать %s: %s": "Could not read %s: %s",
    "В папке уже лежит архив другой съёмочной системы (%s). Укажите другую папку.":
        "The folder already holds an archive of another sensor (%s). Choose a different folder.",
    "Участок слишком велик: %d x %d пикселей. Уменьшите охват или разбейте его на части.":
        "The area is too large: %d x %d pixels. Reduce the extent or split it into parts.",
    "Расчётная сетка: %s": "Analysis grid: %s",
    "%d: в каталоге сцен %d, наблюдений %d, к загрузке %d":
        "%d: scenes in the catalogue %d, observations %d, to download %d",
    "Все найденные наблюдения уже есть в архиве.": "All observations found are already in the archive.",
    "  загружено %d из %d (пригодных %d, облачных %d, сбоев %d), осталось около %.0f мин":
        "  downloaded %d of %d (usable %d, cloudy %d, failed %d), about %.0f min left",
    ("Загрузка завершена за %.1f мин: пригодных наблюдений %d, отброшено по облачности %d, пустых %d, "
     "сбоев %d."):
        ("Download finished in %.1f min: usable observations %d, rejected as cloudy %d, empty %d, "
         "failed %d."),
    # ------------------------------------------ core/composites.py
    "MNDWI (зелёный и средний ИК)": "MNDWI (green and shortwave infrared)",
    "NDWI (зелёный и ближний ИК)": "NDWI (green and near infrared)",
    "В таблице уровня не найдено ни одной пары «дата — значение»: %s":
        "No “date – value” pairs found in the sea level table: %s",
    "Ряд уровня не перекрывается по времени со снимками.":
        "The sea level series does not overlap the imagery in time.",
    "Неизвестный индекс: %s": "Unknown index: %s",
    "В папке нет архива сцен (файл archive.json): %s":
        "The folder has no scene archive (archive.json file): %s",
    "В архиве нет пригодных сцен за выбранные месяцы.":
        "The archive has no usable scenes for the selected months.",
    "Отбор по уровню моря: оставлено %d наблюдений из %d (уровень от %.2f до %.2f).":
        "Selection by sea level: kept %d observations of %d (level from %.2f to %.2f).",
    "За годы %d–%d в архиве нет пригодных сцен.": "The archive has no usable scenes for %d–%d.",
    "Индекс %s, годы %d–%d (лет с данными: %d), наблюдений %d; сетка %dx%d, полос %d.":
        "Index %s, years %d–%d (years with data: %d), observations %d; grid %dx%d, strips %d.",
    "Композиты записаны в %s": "Composites written to %s",
    "Не задано ни одного годового растра.": "No annual rasters given.",
    "У растра не определён код EPSG системы координат: %s":
        "The raster has no EPSG code for its coordinate system: %s",
    "Растр %s лежит в другой сетке, чем растр первого года.":
        "Raster %s is on a different grid from the raster of the first year.",
    # ----------------------------------------------- core/masks.py
    "В папке не найдены годовые композиты индекса (файлы вида mndwi_2020.tif): %s":
        "No annual index composites found in the folder (files like mndwi_2020.tif): %s",
    "В папке нет файлов %s_<год>.tif: %s": "The folder has no %s_<year>.tif files: %s",
    "В папке нет композитов за выбранные годы.": "The folder has no composites for the selected years.",
    "Загружены композиты %s за %d–%d (лет: %d), сетка %dx%d.":
        "Loaded %s composites for %d–%d (years: %d), grid %dx%d.",
    "Композит один: временная маска не применяется (не с чем сравнивать).":
        "Only one composite: the temporal mask is not applied (nothing to compare with).",
    "Временная маска: снято %d пикселей неподтверждённой «суши».":
        "Temporal mask: removed %d pixels of unconfirmed “land”.",
    "Маска водотоков: исключено %.2f км2.": "River mask: excluded %.2f km2.",
    "Слой морской акватории не попадает на воду в пределах участка.":
        "The sea layer does not fall on water within the area.",
    "На участке не найдено открытой воды. Проверьте порог индекса и охват.":
        "No open water found in the area. Check the index threshold and the extent.",
    "Море: крупнейший постоянный водоём, %.1f км2 в пределах участка.":
        "Sea: the largest permanent water body, %.1f km2 within the area.",
    "Море и водоёмы: все постоянные водоёмы шире %.0f м, найдено %d.":
        "Sea and water bodies: all permanent water bodies wider than %.0f m, found %d.",
    "Прибрежная полоса %.0f м: %.1f км2.": "Coastal strip %.0f m: %.1f km2.",
    # -------------------------------------------- core/contours.py
    "%d: береговая линия не выделена (нет данных в прибрежной полосе).":
        "%d: no shoreline extracted (no data in the coastal strip).",
    "%d: длина береговой линии %.1f км.": "%d: shoreline length %.1f km.",
    # ----------------------------------------------- core/rates.py
    "Для оценки темпов нужны береговые линии хотя бы за три года.":
        "Shorelines for at least three years are needed to estimate rates.",
    "Опорного года %s нет среди береговых линий; взят последний год ряда.":
        "Baseline year %s is not among the shorelines; the last year of the series is used.",
    "Береговая линия опорного года пуста.": "The shoreline of the baseline year is empty.",
    "Опорный год %d, точек через %.0f м: %d.": "Baseline year %d, points every %.0f m: %d.",
    "Рассчитаны темпы в %d точках; надёжных (certainty = good): %d.":
        "Rates computed at %d points; reliable (certainty = good): %d.",
    "Обобщённых точек радиуса %.0f м: %d.": "Summary points of radius %.0f m: %d.",
    # ---------------------------------------------- core/gridio.py
    "Grid(EPSG:%d, %dx%d, шаг %g м, начало %.1f/%.1f)":
        "Grid(EPSG:%d, %dx%d, step %g m, origin %.1f/%.1f)",
}
