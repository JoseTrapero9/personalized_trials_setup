"""Participant-facing screen text in the three languages.   t("key", n=3) -> string in state.language."""

from state import state

T = {
    # ---------------- game HUD ----------------
    "status_match": {"en": "FIND THE MATCH!", "es": "¡ENCUENTRA LA COINCIDENCIA!", "de": "FINDE DEN TREFFER!"},
    "status_wait": {"en": "WAIT FOR YOUR INSTRUCTION!", "es": "¡ESPERA TU INSTRUCCIÓN!",
                    "de": "WARTE AUF DEINE ANWEISUNG!"},
    "status_answer": {"en": "ANSWER NOW!", "es": "¡RESPONDE AHORA!", "de": "JETZT ANTWORTEN!"},
    "mode_hard": {"en": "HARD", "es": "DIFÍCIL", "de": "SCHWER"},
    "start_hard_line": {
        "en": "<br><b>HARD MODE</b>",
        "es": "<br><b>MODO DIFÍCIL</b>",
        "de": "<br><b>SCHWERER MODUS</b>",
    },
    "radio_title": {"en": "PLANT RADIO", "es": "RADIO DE LA PLANTA", "de": "WERKSRADIO"},
    "score": {"en": "SCORE", "es": "PUNTOS", "de": "PUNKTE"},
    "next_cp": {"en": "CHECKPOINT IN {n}", "es": "PUNTO DE CONTROL EN {n}", "de": "KONTROLLPUNKT IN {n}"},
    "assembly_mode": {"en": "ASSEMBLY RUNNING", "es": "ENSAMBLAJE EN CURSO", "de": "MONTAGE LÄUFT"},
    "audio_missing": {"en": "RADIO AUDIO MISSING", "es": "FALTA EL AUDIO DE LA RADIO",
                      "de": "RADIO-AUDIO FEHLT"},
    "checkpoint_title": {"en": "CHECKPOINT (ROUND {r}/{m})", "es": "PUNTO DE CONTROL (RONDA {r}/{m})",
                         "de": "KONTROLLPUNKT (RUNDE {r}/{m})"},
    "checkpoint_sub": {"en": "BRING BACK THE EMPTY PIECE!\nTake parts from CONTAINER {c}",
                       "es": "¡REGRESA LA PIEZA VACÍA!\nToma piezas del CONTENEDOR {c}",
                       "de": "LEERES TEIL ZURÜCKBRINGEN!\nTeile aus BEHÄLTER {c} nehmen"},
    "delivery_title": {"en": "DELIVERY ({s}s PAUSE)", "es": "ENTREGA (PAUSA DE {s}s)",
                       "de": "ÜBERGABE ({s}s PAUSE)"},
    "delivery_sub": {"en": "Place the workpiece at {pt} and press {key} now!",
                     "es": "¡Coloca la pieza en {pt} y presiona {key} ahora!",
                     "de": "Lege das Werkstück auf {pt} und drücke jetzt {key}!"},
    "system_failed": {"en": "SYSTEM FAILED\nDELIVER YOUR PIECE TO FIX",
                      "es": "FALLA DEL SISTEMA\nENTREGA TU PIEZA PARA ARREGLARLO",
                      "de": "SYSTEMAUSFALL\nÜBERGIB DEIN TEIL ZUR BEHEBUNG"},

    # ---------------- right panel (battery) ----------------
    "point": {"en": "Point {n}", "es": "Punto {n}", "de": "Punkt {n}"},
    "key_left": {"en": "Left", "es": "Izquierda", "de": "Links"},
    "key_right": {"en": "Right", "es": "Derecha", "de": "Rechts"},
    "advance": {"en": "Answer the radio to reach the next checkpoint.",
                "es": "Responde a la radio para llegar al siguiente punto de control.",
                "de": "Reagiere auf das Radio, um den nächsten Kontrollpunkt zu erreichen."},
    "solve_header": {"en": "SOLVE THE BATTERY & KEEP LISTENING", "es": "RESUELVE LA BATERÍA Y SIGUE ESCUCHANDO",
                     "de": "LÖSE DIE BATTERIE & HÖR WEITER ZU"},
    "deliver_hint": {"en": 'Press <b>D</b> for a {s}s pause, then place at <b>{pt}</b> & press <b>{key}</b>.',
                     "es": 'Presiona <b>D</b> para una pausa de {s}s, luego coloca en <b>{pt}</b> y presiona <b>{key}</b>.',
                     "de": 'Drücke <b>D</b> für {s}s Pause, dann auf <b>{pt}</b> legen & <b>{key}</b> drücken.'},
    "delivery_active": {"en": "<b>DELIVERY WINDOW ({s}s)</b><br>Place the workpiece at <b>{pt}</b> and press <b>{key}</b>!",
                        "es": "<b>VENTANA DE ENTREGA ({s}s)</b><br>¡Coloca la pieza en <b>{pt}</b> y presiona <b>{key}</b>!",
                        "de": "<b>ÜBERGABEFENSTER ({s}s)</b><br>Lege das Werkstück auf <b>{pt}</b> und drücke <b>{key}</b>!"},
    "warning_finish": {"en": "WARNING - FINISH", "es": "AVISO - TERMINA", "de": "WARNUNG - FERTIG MACHEN"},
    "failed_short": {"en": "SYSTEM FAILED", "es": "FALLA DEL SISTEMA", "de": "SYSTEMAUSFALL"},
    "round": {"en": "ROUND {r} / {m}", "es": "RONDA {r} / {m}", "de": "RUNDE {r} / {m}"},

    # ---------------- start screen ----------------
    "start_title_training": {"en": "Training Session", "es": "Sesión de práctica", "de": "Trainingsphase"},
    "start_title_cond": {"en": "Block {c}", "es": "Bloque {c}", "de": "Block {c}"},
    "start_body": {
        "en": "1. Listen to the <b>plant radio</b>. When something breaks, it tells you which buttons to press.<br>"
              "2. Find those buttons on the screen and press them with <b>← ↑ →</b> (left, middle, right).<br>"
              "3. After some problems the radio pauses for <b>{r}s</b>: take parts from Container I or II.<br>"
              "4. The screen splits: build the battery while you keep answering the radio.<br>"
              "5. Press <b>\"D: DELIVER\"</b> for a <b>{d}s</b> pause, place the piece and press the Point button.<br><br>"
              "Rounds: <b>{rounds}</b>",
        "es": "1. Escucha la <b>radio de la planta</b>. Cuando algo falla, te dice qué botones presionar.<br>"
              "2. Busca esos botones en la pantalla y presiónalos con <b>← ↑ →</b> (izquierda, centro, derecha).<br>"
              "3. Después de unos problemas la radio hace una pausa de <b>{r}s</b>: toma piezas del Contenedor I o II.<br>"
              "4. La pantalla se divide: arma la batería mientras sigues respondiendo a la radio.<br>"
              "5. Presiona <b>\"D: DELIVER\"</b> para una pausa de <b>{d}s</b>, coloca la pieza y presiona el botón del Punto.<br><br>"
              "Rondas: <b>{rounds}</b>",
        "de": "1. Hör dem <b>Werksradio</b> zu. Wenn etwas kaputtgeht, sagt es dir, welche Knöpfe du drücken musst.<br>"
              "2. Finde diese Knöpfe auf dem Bildschirm und drücke sie mit <b>← ↑ →</b> (links, Mitte, rechts).<br>"
              "3. Nach einige Problemen pausiert das Radio <b>{r}s</b>: nimm Teile aus Behälter I oder II.<br>"
              "4. Der Bildschirm teilt sich: baue die Batterie und reagiere weiter auf das Radio.<br>"
              "5. Drück <b>\"D: DELIVER\"</b> für <b>{d}s</b> Pause, lege das Teil ab und drücke den Punkt-Knopf.<br><br>"
              "Runden: <b>{rounds}</b>",
    },
    "start_button": {"en": "Start", "es": "Comenzar", "de": "Start"},
    "preparing": {"en": "Get ready...", "es": "Prepárate...", "de": "Gleich geht's los..."},

    # ---------------- tutorial ----------------
    "tut_header": {"en": "TRAINING TUTORIAL — STEP {i} / {n}", "es": "TUTORIAL — PASO {i} / {n}",
                   "de": "TUTORIAL — SCHRITT {i} / {n}"},
    "tut_back": {"en": "← Back", "es": "← Atrás", "de": "← Zurück"},
    "tut_next": {"en": "Next →", "es": "Siguiente →", "de": "Weiter →"},
    "tut_start": {"en": "Start Practice →", "es": "Empezar práctica →", "de": "Training starten →"},
    "tut_continue": {"en": "Continue →", "es": "Continuar →", "de": "Weiter →"},
    "block_header": {"en": "PRACTICE BLOCK {i} / {n}", "es": "BLOQUE DE PRÁCTICA {i} / {n}",
                     "de": "ÜBUNGSBLOCK {i} / {n}"},
    "block_start": {"en": "Start block →", "es": "Empezar bloque →", "de": "Block starten →"},
    "demo_pos": {"en": "1 · Right cue", "es": "1 · Señal de bien", "de": "1 · Signal richtig"},
    "demo_neg": {"en": "2 · Wrong cue", "es": "2 · Señal de mal", "de": "2 · Signal falsch"},
    "start_title_block": {"en": "Practice block {i} of {n}: {name}", "es": "Bloque de práctica {i} de {n}: {name}",
                          "de": "Übungsblock {i} von {n}: {name}"},
}

HARD_TUTORIAL_STEP = {
    "en": ("Hard mode · Find the match",
           "While you wait for the next instruction, the buttons keep changing, and each time <b>one</b> "
           "button's color <b>matches</b> its word (for example a <b>red</b> button that says RED).<br><br>"
           "Press it before the buttons change: <b>+{p} points</b>. You get <b>one try</b> per change, "
           "and missing it costs nothing.<br><br>"
           "While the radio gives an instruction (<b>WAIT FOR YOUR INSTRUCTION!</b>) the buttons spin and the "
           "arrows are <b>locked</b>. At <b>ANSWER NOW!</b> the real buttons appear: press the ones it said.<br><br>"
           "Radio instructions now give <b>double points</b>, and mistakes cost <b>double</b>."),
    "es": ("Modo difícil · Encuentra la coincidencia",
           "Mientras esperas la siguiente instrucción, los botones siguen cambiando, y cada vez <b>un</b> "
           "botón tiene el color que <b>coincide</b> con su palabra (por ejemplo un botón <b>rojo</b> que dice ROJO).<br><br>"
           "Presiónalo antes de que cambien los botones: <b>+{p} puntos</b>. Tienes <b>un intento</b> por cambio, "
           "y si no lo presionas no pierdes puntos.<br><br>"
           "Mientras la radio da una instrucción (<b>¡ESPERA TU INSTRUCCIÓN!</b>) los botones giran y las "
           "flechas están <b>bloqueadas</b>. En <b>¡RESPONDE AHORA!</b> aparecen los botones reales: presiona los que dijo.<br><br>"
           "Las instrucciones de la radio ahora valen <b>el doble</b>, y los errores cuestan <b>el doble</b>."),
    "de": ("Schwerer Modus · Finde den Treffer",
           "Während du auf die nächste Anweisung wartest, wechseln die Knöpfe weiter, und jedes Mal "
           "<b>passt</b> bei <b>einem</b> Knopf die Farbe zum Wort (zum Beispiel ein <b>roter</b> Knopf mit ROT).<br><br>"
           "Drücke ihn, bevor die Knöpfe wechseln: <b>+{p} Punkte</b>. Du hast <b>einen Versuch</b> pro Wechsel, "
           "und Verpassen kostet nichts.<br><br>"
           "Während das Radio eine Anweisung gibt (<b>WARTE AUF DEINE ANWEISUNG!</b>), drehen sich die Knöpfe und die "
           "Pfeiltasten sind <b>gesperrt</b>. Bei <b>JETZT ANTWORTEN!</b> erscheinen die echten Knöpfe: drücke die genannten.<br><br>"
           "Radio-Anweisungen geben jetzt <b>doppelte Punkte</b>, und Fehler kosten <b>doppelt</b>."),
}

TUTORIAL = {
    "en": [
        ("Two tasks at the same time",
         "Today you keep a power plant running <b>and</b> build batteries, both at the same time.<br><br>"
         "• <b>Radio task</b>: listen to the plant radio and press buttons with <b>←</b> <b>↑</b> <b>→</b><br>"
         "• <b>Battery task</b>: build batteries on the tray in front of you<br><br>"
         "Both tasks count, so try to keep both going."),
        ("Radio · Listen",
         "The plant radio talks all the time.<br><br>"
         "When something breaks (<i>\"Oh no, a short circuit!\"</i>), the radio tells you "
         "<b>which buttons to press</b>. It says it only once, so keep listening."),
        ("Radio · Color or word?",
         "Every button has a <b>color</b> and a <b>word</b>, and they never match.<br><br>"
         "• <i>\"the red button\"</i> → the button that <b>is red</b><br>"
         "• <i>\"the button labeled red\"</i> → the button with the <b>word RED</b><br><br>"
         "If the radio names several buttons, press them <b>in that order</b>."),
        ("Radio · Which key?",
         "Left button = <b>←</b> &nbsp; Middle button = <b>↑</b> &nbsp; Right button = <b>→</b><br><br>"
         "The buttons <b>stop changing</b> while a problem is active.<br>"
         "One wrong key or running out of time = problem failed, you lose points, and the radio goes on."),
        ("Checkpoints",
         "After <b>{n} problems</b> the radio pauses for <b>{r} seconds</b>: bring back the empty piece "
         "and take parts from <b>Container I or II</b> (the screen tells you which)."),
        ("Battery · Make the sum",
         "Then the screen splits. On the right you see the <b>sum</b> and <b>which batteries</b> to use.<br><br>"
         "Values: <b>Blue = 1 &nbsp; Red = 2 &nbsp; Yellow = 3 &nbsp; Green = 4</b><br>"
         "Slot 1 counts <b>×1</b>, slot 2 <b>×2</b>, slot 3 <b>×3</b><br><br>"
         "Example: <i>sum 18, use 1 Blue and 2 Green</i> → <b>Green · Blue · Green</b> = 4 + 2 + 12 = 18<br><br>"
         "Keep answering the radio while you build."),
        ("Battery · Deliver with D",
         "Finished? Press <b>D</b>: the radio pauses for <b>{d} seconds</b>. Place the tray at "
         "<b>Point 1</b> or <b>Point 2</b> (the screen tells you which) and press that point's button.<br><br>"
         "You have <b>{s} seconds</b> per battery. At 0, <b>SYSTEM FAILED</b> flashes until you deliver."),
        ("How the practice works",
         "You practise in <b>{b} short blocks of {k} rounds</b>:<br><br>"
         "{blocks}<br><br>"
         "Before each block, one slide shows how its feedback works."),
    ],
    "es": [
        ("Dos tareas al mismo tiempo",
         "Hoy mantienes funcionando una planta de energía <b>y</b> armas baterías, las dos cosas a la vez.<br><br>"
         "• <b>Tarea de la radio</b>: escucha la radio de la planta y presiona botones con <b>←</b> <b>↑</b> <b>→</b><br>"
         "• <b>Tarea de las baterías</b>: arma baterías en la bandeja que tienes enfrente<br><br>"
         "Las dos tareas cuentan, así que intenta mantener ambas."),
        ("Radio · Escucha",
         "La radio de la planta habla todo el tiempo.<br><br>"
         "Cuando algo falla (<i>\"¡Ay no, un cortocircuito!\"</i>), la radio te dice "
         "<b>qué botones presionar</b>. Lo dice una sola vez, así que no dejes de escuchar."),
        ("Radio · ¿Color o palabra?",
         "Cada botón tiene un <b>color</b> y una <b>palabra</b>, y nunca coinciden.<br><br>"
         "• <i>\"el botón rojo\"</i> → el botón que <b>es rojo</b><br>"
         "• <i>\"el botón que dice rojo\"</i> → el botón con la <b>palabra ROJO</b><br><br>"
         "Si la radio nombra varios botones, presiónalos <b>en ese orden</b>."),
        ("Radio · ¿Qué tecla?",
         "Botón izquierdo = <b>←</b> &nbsp; Botón del centro = <b>↑</b> &nbsp; Botón derecho = <b>→</b><br><br>"
         "Los botones <b>dejan de cambiar</b> mientras hay un problema activo.<br>"
         "Una tecla equivocada o quedarte sin tiempo = problema fallido, pierdes puntos y la radio sigue."),
        ("Puntos de control",
         "Después de <b>{n} problemas</b> la radio hace una pausa de <b>{r} segundos</b>: regresa la pieza vacía "
         "y toma piezas del <b>Contenedor I o II</b> (la pantalla te dice cuál)."),
        ("Batería · Haz la suma",
         "Luego la pantalla se divide. A la derecha ves la <b>suma</b> y <b>qué baterías</b> usar.<br><br>"
         "Valores: <b>Azul = 1 &nbsp; Rojo = 2 &nbsp; Amarillo = 3 &nbsp; Verde = 4</b><br>"
         "La ranura 1 cuenta <b>×1</b>, la ranura 2 <b>×2</b>, la ranura 3 <b>×3</b><br><br>"
         "Ejemplo: <i>suma 18, usa 1 Azul y 2 Verdes</i> → <b>Verde · Azul · Verde</b> = 4 + 2 + 12 = 18<br><br>"
         "Sigue respondiendo a la radio mientras armas."),
        ("Batería · Entrega con D",
         "¿Terminaste? Presiona <b>D</b>: la radio hace una pausa de <b>{d} segundos</b>. Coloca la bandeja en el "
         "<b>Punto 1</b> o el <b>Punto 2</b> (la pantalla te dice cuál) y presiona el botón de ese punto.<br><br>"
         "Tienes <b>{s} segundos</b> por batería. En 0, <b>FALLA DEL SISTEMA</b> parpadea hasta que entregues."),
        ("Cómo funciona la práctica",
         "Practicas en <b>{b} bloques cortos de {k} rondas</b>:<br><br>"
         "{blocks}<br><br>"
         "Antes de cada bloque, una diapositiva te muestra cómo funciona su retroalimentación."),
    ],
    "de": [
        ("Zwei Aufgaben gleichzeitig",
         "Heute hältst du ein Kraftwerk am Laufen <b>und</b> baust Batterien, beides gleichzeitig.<br><br>"
         "• <b>Radio-Aufgabe</b>: hör dem Werksradio zu und drücke Knöpfe mit <b>←</b> <b>↑</b> <b>→</b><br>"
         "• <b>Batterie-Aufgabe</b>: baue Batterien auf dem Tablett vor dir<br><br>"
         "Beide Aufgaben zählen, also versuche, beide am Laufen zu halten."),
        ("Radio · Zuhören",
         "Das Werksradio redet die ganze Zeit.<br><br>"
         "Wenn etwas kaputtgeht (<i>\"Oh nein, Kurzschluss!\"</i>), sagt dir das Radio, "
         "<b>welche Knöpfe du drücken musst</b>. Es sagt es nur einmal, also hör gut zu."),
        ("Radio · Farbe oder Wort?",
         "Jeder Knopf hat eine <b>Farbe</b> und ein <b>Wort</b>, und sie passen nie zusammen.<br><br>"
         "• <i>\"den roten Knopf\"</i> → der Knopf, der <b>rot ist</b><br>"
         "• <i>\"den Knopf mit der Aufschrift Rot\"</i> → der Knopf mit dem <b>Wort ROT</b><br><br>"
         "Nennt das Radio mehrere Knöpfe, drücke sie <b>in dieser Reihenfolge</b>."),
        ("Radio · Welche Taste?",
         "Linker Knopf = <b>←</b> &nbsp; Mittlerer Knopf = <b>↑</b> &nbsp; Rechter Knopf = <b>→</b><br><br>"
         "Während ein Problem läuft, <b>ändern sich die Knöpfe nicht</b>.<br>"
         "Eine falsche Taste oder zu langsam = Problem verloren, du verlierst Punkte, und das Radio redet weiter."),
        ("Kontrollpunkte",
         "Nach <b>{n} Problemen</b> pausiert das Radio <b>{r} Sekunden</b>: bring das leere Teil zurück "
         "und nimm Teile aus <b>Behälter I oder II</b> (der Bildschirm sagt dir, welcher)."),
        ("Batterie · Die Summe bilden",
         "Dann teilt sich der Bildschirm. Rechts siehst du die <b>Summe</b> und <b>welche Batterien</b> du nimmst.<br><br>"
         "Werte: <b>Blau = 1 &nbsp; Rot = 2 &nbsp; Gelb = 3 &nbsp; Grün = 4</b><br>"
         "Platz 1 zählt <b>×1</b>, Platz 2 <b>×2</b>, Platz 3 <b>×3</b><br><br>"
         "Beispiel: <i>Summe 18, nimm 1 Blau und 2 Grün</i> → <b>Grün · Blau · Grün</b> = 4 + 2 + 12 = 18<br><br>"
         "Reagiere beim Bauen weiter auf das Radio."),
        ("Batterie · Mit D übergeben",
         "Fertig? Drücke <b>D</b>: das Radio pausiert <b>{d} Sekunden</b>. Stelle das Tablett auf "
         "<b>Punkt 1</b> oder <b>Punkt 2</b> (der Bildschirm sagt dir, welchen) und drücke den Knopf dieses Punkts.<br><br>"
         "Du hast <b>{s} Sekunden</b> pro Batterie. Bei 0 blinkt <b>SYSTEMAUSFALL</b>, bis du übergibst."),
        ("So läuft das Training",
         "Du übst in <b>{b} kurzen Blöcken mit je {k} Runden</b>:<br><br>"
         "{blocks}<br><br>"
         "Vor jedem Block zeigt dir eine Folie, wie sein Feedback funktioniert."),
    ],
}

# Names of the training blocks / conditions as the participant sees them
BLOCK_NAMES = {
    "baseline": {"en": "no feedback", "es": "sin retroalimentación", "de": "ohne Feedback"},
    "audio": {"en": "sound feedback", "es": "retroalimentación por sonido", "de": "Ton-Feedback"},
    "audio_haptic": {"en": "sound + vest feedback", "es": "retroalimentación por sonido + chaleco",
                     "de": "Ton- + Westen-Feedback"},
    "haptic": {"en": "vest feedback", "es": "retroalimentación por chaleco", "de": "Westen-Feedback"},
}

# How each cue is described on the cue slides (depends on the audio cue mode and the vest patterns in config.py)
CUE_WORDS = {
    "audio_pos": {"voice": {"en": "a voice says <b>\"input correct\"</b>", "es": "una voz dice <b>\"input correct\"</b>",
                            "de": "eine Stimme sagt <b>\"input correct\"</b>"},
                  "tone": {"en": "a <b>short bright sound</b>", "es": "un <b>sonido corto y agudo</b>",
                           "de": "ein <b>kurzer heller Ton</b>"}},
    "audio_neg": {"voice": {"en": "a voice says <b>\"input incorrect\"</b>", "es": "una voz dice <b>\"input incorrect\"</b>",
                            "de": "eine Stimme sagt <b>\"input incorrect\"</b>"},
                  "tone": {"en": "an <b>error sound</b>", "es": "un <b>sonido de error</b>", "de": "ein <b>Fehlerton</b>"}},
    "positive_3": {"en": "a <b>soft swell</b>", "es": "una <b>ola suave</b>", "de": "eine <b>sanfte Welle</b>"},
    "negative_2": {"en": "<b>three strong pulses</b>", "es": "<b>tres pulsos fuertes</b>", "de": "<b>drei starke Stöße</b>"},
    "vest_any": {"en": "a <b>vibration</b>", "es": "una <b>vibración</b>", "de": "eine <b>Vibration</b>"},
    "VestBack": {"en": "on your back", "es": "en tu espalda", "de": "am Rücken"},
    "VestFront": {"en": "on your chest", "es": "en tu pecho", "de": "an der Brust"},
}

CUE_SLIDES = {
    "baseline": {
        "en": ("No feedback",
               "In this block the system gives you <b>no feedback</b> about your batteries.<br><br>"
               "Check yourself that the colors and the sum are right before you deliver."),
        "es": ("Sin retroalimentación",
               "En este bloque el sistema <b>no te da retroalimentación</b> sobre tus baterías.<br><br>"
               "Revisa tú mismo que los colores y la suma estén bien antes de entregar."),
        "de": ("Ohne Feedback",
               "In diesem Block gibt dir das System <b>kein Feedback</b> zu deinen Batterien.<br><br>"
               "Prüfe selbst, ob Farben und Summe stimmen, bevor du übergibst."),
    },
    "intro": {
        "en": "Each time you put a battery in a slot, the system checks it right away:",
        "es": "Cada vez que pones una batería en una ranura, el sistema la revisa de inmediato:",
        "de": "Jedes Mal, wenn du eine Batterie in einen Platz steckst, prüft das System sie sofort:",
    },
    "audio_line": {
        "en": "<b>In your headphones</b><br>✔ {pos} → this battery is <b>right</b><br>"
              "✘ {neg} → this battery is <b>wrong</b>",
        "es": "<b>En tus audífonos</b><br>✔ {pos} → esta batería está <b>bien</b><br>"
              "✘ {neg} → esta batería está <b>mal</b>",
        "de": "<b>In deinen Kopfhörern</b><br>✔ {pos} → diese Batterie ist <b>richtig</b><br>"
              "✘ {neg} → diese Batterie ist <b>falsch</b>",
    },
    "vest_line": {
        "en": "<b>On the vest</b><br>✔ {pos} <b>{pos_loc}</b> → <b>right</b><br>"
              "✘ {neg} <b>{neg_loc}</b> → <b>wrong</b>",
        "es": "<b>En el chaleco</b><br>✔ {pos} <b>{pos_loc}</b> → <b>bien</b><br>"
              "✘ {neg} <b>{neg_loc}</b> → <b>mal</b>",
        "de": "<b>An der Weste</b><br>✔ {pos} <b>{pos_loc}</b> → <b>richtig</b><br>"
              "✘ {neg} <b>{neg_loc}</b> → <b>falsch</b>",
    },
    "after": {
        "en": "Wrong battery? Take it out and put in the right one: every battery you place gets its own cue.",
        "es": "¿Batería equivocada? Sácala y pon la correcta: cada batería que colocas recibe su propia señal.",
        "de": "Falsche Batterie? Nimm sie heraus und setze die richtige ein: jede Batterie bekommt ihr eigenes Signal.",
    },
    "pickup": {
        "en": "At a checkpoint, a double pulse on your <b>right side</b> reminds you to pick up new parts.",
        "es": "En un punto de control, un pulso doble en tu <b>lado derecho</b> te recuerda tomar piezas nuevas.",
        "de": "An einem Kontrollpunkt erinnert dich ein doppelter Impuls an deiner <b>rechten Seite</b>, neue Teile zu holen.",
    },
    "try": {
        "en": "Try them now: <b>1</b> = right cue, <b>2</b> = wrong cue",
        "es": "Pruébalas ahora: <b>1</b> = señal de bien, <b>2</b> = señal de mal",
        "de": "Probiere sie aus: <b>1</b> = Signal richtig, <b>2</b> = Signal falsch",
    },
}


def _lang(lang=None):
    lang = lang or state.language
    return lang if lang in ("en", "es", "de") else "en"


def block_name(condition, lang=None):
    return BLOCK_NAMES[condition][_lang(lang)]


def cue_slide(condition, lang=None, audio_cue_mode=None):
    """(title, body) of the slide that explains the feedback cues of one condition."""
    from config import (BATTERY_CUE_CONDITIONS, HAPTIC_CORRECT_PATTERN, HAPTIC_CORRECT_POSITION,
                        HAPTIC_INCORRECT_PATTERN, HAPTIC_INCORRECT_POSITION)
    lang = _lang(lang)
    if condition not in BATTERY_CUE_CONDITIONS:
        return CUE_SLIDES["baseline"][lang]
    mode = audio_cue_mode if audio_cue_mode in ("voice", "tone") else "voice"
    channels = BATTERY_CUE_CONDITIONS[condition]
    parts = [CUE_SLIDES["intro"][lang]]
    if "audio" in channels:
        parts.append(CUE_SLIDES["audio_line"][lang].format(pos=CUE_WORDS["audio_pos"][mode][lang],
                                                           neg=CUE_WORDS["audio_neg"][mode][lang]))
    if "haptic" in channels:
        vest = lambda pattern: CUE_WORDS.get(pattern, CUE_WORDS["vest_any"])[lang]
        parts.append(CUE_SLIDES["vest_line"][lang].format(
            pos=vest(HAPTIC_CORRECT_PATTERN), neg=vest(HAPTIC_INCORRECT_PATTERN),
            pos_loc=CUE_WORDS[HAPTIC_CORRECT_POSITION][lang], neg_loc=CUE_WORDS[HAPTIC_INCORRECT_POSITION][lang]))
    parts.append(CUE_SLIDES["after"][lang])
    if "haptic" in channels:
        parts.append(CUE_SLIDES["pickup"][lang])
    parts.append(f"<i>{CUE_SLIDES['try'][lang]}</i>")
    name = block_name(condition, lang)
    return name[:1].upper() + name[1:], "<br><br>".join(parts)


def t(text_id, /, **kw):
    lang = state.language if state.language in ("en", "es", "de") else "en"
    s = T[text_id].get(lang) or T[text_id]["en"]
    return s.format(**kw) if kw else s
