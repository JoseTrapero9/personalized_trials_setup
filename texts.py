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
        "en": "<br><b>HARD MODE:</b> between instructions, press the one button whose color matches its word "
              "(<b>+{p}</b>, one try per change, missing costs nothing). Instructions count <b>double</b>, "
              "mistakes cost <b>double</b>.",
        "es": "<br><b>MODO DIFÍCIL:</b> entre instrucciones, presiona el único botón cuyo color coincide con su palabra "
              "(<b>+{p}</b>, un intento por cambio, fallar no quita puntos). Las instrucciones valen <b>el doble</b> "
              "y los errores cuestan <b>el doble</b>.",
        "de": "<br><b>SCHWERER MODUS:</b> zwischen den Anweisungen drücke den einen Knopf, dessen Farbe zu seinem Wort "
              "passt (<b>+{p}</b>, ein Versuch pro Wechsel, Verpassen kostet nichts). Anweisungen zählen "
              "<b>doppelt</b>, Fehler kosten <b>doppelt</b>.",
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
    "deliver_hint": {"en": 'Say <b>"DELIVER"</b> (or press <b>D</b>) for a {s}s pause, then place at <b>{pt}</b> & press <b>{key}</b>.',
                     "es": 'Di <b>"DELIVER"</b> (o presiona <b>D</b>) para una pausa de {s}s, luego coloca en <b>{pt}</b> y presiona <b>{key}</b>.',
                     "de": 'Sag <b>"DELIVER"</b> (oder drücke <b>D</b>) für {s}s Pause, dann auf <b>{pt}</b> legen & <b>{key}</b> drücken.'},
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
              "3. After <b>{n} problems</b> the radio pauses for <b>{r}s</b>: take parts from Container I or II.<br>"
              "4. The screen splits: build the battery while you keep answering the radio.<br>"
              "5. Say <b>\"DELIVER\"</b> for a <b>{d}s</b> pause, place the piece and press the Point button.<br><br>"
              "Rounds: <b>{rounds}</b>",
        "es": "1. Escucha la <b>radio de la planta</b>. Cuando algo falla, te dice qué botones presionar.<br>"
              "2. Busca esos botones en la pantalla y presiónalos con <b>← ↑ →</b> (izquierda, centro, derecha).<br>"
              "3. Después de <b>{n} problemas</b> la radio hace una pausa de <b>{r}s</b>: toma piezas del Contenedor I o II.<br>"
              "4. La pantalla se divide: arma la batería mientras sigues respondiendo a la radio.<br>"
              "5. Di <b>\"DELIVER\"</b> para una pausa de <b>{d}s</b>, coloca la pieza y presiona el botón del Punto.<br><br>"
              "Rondas: <b>{rounds}</b>",
        "de": "1. Hör dem <b>Werksradio</b> zu. Wenn etwas kaputtgeht, sagt es dir, welche Knöpfe du drücken musst.<br>"
              "2. Finde diese Knöpfe auf dem Bildschirm und drücke sie mit <b>← ↑ →</b> (links, Mitte, rechts).<br>"
              "3. Nach <b>{n} Problemen</b> pausiert das Radio <b>{r}s</b>: nimm Teile aus Behälter I oder II.<br>"
              "4. Der Bildschirm teilt sich: baue die Batterie und reagiere weiter auf das Radio.<br>"
              "5. Sag <b>\"DELIVER\"</b> für <b>{d}s</b> Pause, lege das Teil ab und drücke den Punkt-Knopf.<br><br>"
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
        ("Welcome to the control room",
         "You will keep a power plant running while you assemble battery workpieces.<br><br>"
         "For the plant you only need <b>three keys</b>: <b>←</b> <b>↑</b> <b>→</b>"),
        ("1 · Listen to the radio",
         "The plant radio talks all the time. Most of it is just chatter.<br><br>"
         "When something breaks (<i>\"Oh no, a short circuit!\"</i>), the radio tells you "
         "<b>which buttons to press</b>. It says it only once, so keep listening."),
        ("2 · Color or word?",
         "Every button has a <b>color</b> and a <b>word</b>, and they never match.<br><br>"
         "• <i>\"the red button\"</i> → the button that <b>is red</b><br>"
         "• <i>\"the button labeled red\"</i> → the button with the <b>word RED</b><br><br>"
         "If the radio names several buttons, press them <b>in that order</b>."),
        ("3 · Where is the button?",
         "The buttons keep changing. They <b>stop changing</b> while a problem is active.<br><br>"
         "Left button = <b>←</b> &nbsp; Middle button = <b>↑</b> &nbsp; Right button = <b>→</b><br><br>"
         "One wrong key or running out of time = problem failed, you lose points, and the radio goes on."),
        ("4 · Checkpoints",
         "After <b>{n} problems</b> the radio pauses for <b>{r} seconds</b>: bring back the empty piece "
         "and take parts from <b>Container I or II</b>.<br><br>"
         "Problems during the battery task do <b>not</b> count toward the next checkpoint."),
        ("5 · Battery and \"DELIVER\"",
         "The screen splits: solve the battery on the right <b>while you keep answering the radio</b>.<br><br>"
         "When your piece is finished, say <b>\"DELIVER\"</b>: you get a <b>{d}-second pause</b> to place it "
         "and press the <b>Point 1</b> or <b>Point 2</b> button.<br>"
         "If the timer reaches 0, <b>SYSTEM FAILED</b> flashes until you deliver."),
    ],
    "es": [
        ("Bienvenido a la sala de control",
         "Vas a mantener funcionando una planta de energía mientras armas piezas de batería.<br><br>"
         "Para la planta solo necesitas <b>tres teclas</b>: <b>←</b> <b>↑</b> <b>→</b>"),
        ("1 · Escucha la radio",
         "La radio de la planta habla todo el tiempo. Casi todo es plática.<br><br>"
         "Cuando algo falla (<i>\"¡Ay no, un cortocircuito!\"</i>), la radio te dice "
         "<b>qué botones presionar</b>. Lo dice una sola vez, así que no dejes de escuchar."),
        ("2 · ¿Color o palabra?",
         "Cada botón tiene un <b>color</b> y una <b>palabra</b>, y nunca coinciden.<br><br>"
         "• <i>\"el botón rojo\"</i> → el botón que <b>es rojo</b><br>"
         "• <i>\"el botón que dice rojo\"</i> → el botón con la <b>palabra ROJO</b><br><br>"
         "Si la radio nombra varios botones, presiónalos <b>en ese orden</b>."),
        ("3 · ¿Dónde está el botón?",
         "Los botones cambian todo el tiempo. <b>Dejan de cambiar</b> mientras hay un problema activo.<br><br>"
         "Botón izquierdo = <b>←</b> &nbsp; Botón del centro = <b>↑</b> &nbsp; Botón derecho = <b>→</b><br><br>"
         "Una tecla equivocada o quedarte sin tiempo = problema fallido, pierdes puntos y la radio sigue."),
        ("4 · Puntos de control",
         "Después de <b>{n} problemas</b> la radio hace una pausa de <b>{r} segundos</b>: regresa la pieza vacía "
         "y toma piezas del <b>Contenedor I o II</b>.<br><br>"
         "Los problemas durante la tarea de la batería <b>no</b> cuentan para el siguiente punto de control."),
        ("5 · Batería y \"DELIVER\"",
         "La pantalla se divide: resuelve la batería a la derecha <b>mientras sigues respondiendo a la radio</b>.<br><br>"
         "Cuando tu pieza esté terminada, di <b>\"DELIVER\"</b>: tienes una <b>pausa de {d} segundos</b> para colocarla "
         "y presionar el botón <b>Punto 1</b> o <b>Punto 2</b>.<br>"
         "Si el tiempo llega a 0, <b>FALLA DEL SISTEMA</b> parpadea hasta que entregues."),
    ],
    "de": [
        ("Willkommen in der Leitwarte",
         "Du hältst ein Kraftwerk am Laufen, während du Batterie-Werkstücke montierst.<br><br>"
         "Für das Kraftwerk brauchst du nur <b>drei Tasten</b>: <b>←</b> <b>↑</b> <b>→</b>"),
        ("1 · Hör dem Radio zu",
         "Das Werksradio redet die ganze Zeit. Das meiste ist nur Geplauder.<br><br>"
         "Wenn etwas kaputtgeht (<i>\"Oh nein, Kurzschluss!\"</i>), sagt dir das Radio, "
         "<b>welche Knöpfe du drücken musst</b>. Es sagt es nur einmal, also hör gut zu."),
        ("2 · Farbe oder Wort?",
         "Jeder Knopf hat eine <b>Farbe</b> und ein <b>Wort</b>, und sie passen nie zusammen.<br><br>"
         "• <i>\"den roten Knopf\"</i> → der Knopf, der <b>rot ist</b><br>"
         "• <i>\"den Knopf mit der Aufschrift Rot\"</i> → der Knopf mit dem <b>Wort ROT</b><br><br>"
         "Nennt das Radio mehrere Knöpfe, drücke sie <b>in dieser Reihenfolge</b>."),
        ("3 · Wo ist der Knopf?",
         "Die Knöpfe ändern sich ständig. Während ein Problem läuft, <b>ändern sie sich nicht</b>.<br><br>"
         "Linker Knopf = <b>←</b> &nbsp; Mittlerer Knopf = <b>↑</b> &nbsp; Rechter Knopf = <b>→</b><br><br>"
         "Eine falsche Taste oder zu langsam = Problem verloren, du verlierst Punkte, und das Radio redet weiter."),
        ("4 · Kontrollpunkte",
         "Nach <b>{n} Problemen</b> pausiert das Radio <b>{r} Sekunden</b>: bring das leere Teil zurück "
         "und nimm Teile aus <b>Behälter I oder II</b>.<br><br>"
         "Probleme während der Batterie-Aufgabe zählen <b>nicht</b> für den nächsten Kontrollpunkt."),
        ("5 · Batterie und \"DELIVER\"",
         "Der Bildschirm teilt sich: löse rechts die Batterie <b>und reagiere weiter auf das Radio</b>.<br><br>"
         "Wenn dein Teil fertig ist, sag <b>\"DELIVER\"</b>: du bekommst <b>{d} Sekunden Pause</b>, um es abzulegen "
         "und den Knopf <b>Punkt 1</b> oder <b>Punkt 2</b> zu drücken.<br>"
         "Wenn die Zeit 0 erreicht, blinkt <b>SYSTEMAUSFALL</b>, bis du übergibst."),
    ],
}


def t(text_id, /, **kw):
    lang = state.language if state.language in ("en", "es", "de") else "en"
    s = T[text_id].get(lang) or T[text_id]["en"]
    return s.format(**kw) if kw else s
