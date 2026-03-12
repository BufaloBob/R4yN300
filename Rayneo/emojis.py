import re
import os
import requests
import unicodedata
from functools import lru_cache
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

EMOJI_DICT = {
    # ── AMORE / ROMANTICISMO ──
    "❤️": ["corazon", "amor", "te amo", "te quiero", "enamorado", "enamorada", "amar", "cariño", "mi amor", "vida mia", "corazon mio", "mi vida", "novio", "novia", "esposa", "esposo", "papi", "mami"],
    "💖": ["anhelo", "anhelar", "te anhelo"],
    "❤️‍🔥": ["pasion", "loco por ti", "loca por ti", "obsesion", "obsesionado", "no te puedo olvidar", "me tienes loco", "me tienes loca", "fuego en el alma", "ardiendo por ti", "deseo loco"],
    "💔": ["Tú me rompiste el corazón","rompo corazone'""rota", "roto", "desamor", "ex", "toxic", "toxica", "toxico", "dolor de amor", "herida", "traicion amor", "mentira","mentira'", "engaño", "me fallo", "me falla", "te bote", "Te Boté", "te fuiste", "ya no estas", "me dejo", "me deja", "olvidame", "no te merecia", "dolor"],
    "💋": ["beso", "besos", "besito", "besitos", "besarte","labios", "boca", "muah", "mwah", "muack", "smack", "chu", "chuu", "besar", "besame", "bésame", "dame un beso", "labios", "kiss", "kisses", "kissing"],
    "🫦": ["clavé","agarra'","Sé que quieres", "comer", "comemos", "comerte","comersela","chocan", "choca", "freaky", "friki", "sexy", "sex", "sensual", "tentacion", "provocar", "bellaqueo", "superbellaca", "bellaca", "bellaco", "ganas", "caliente de ganas", "cosa rica", "cosas malas", "picante", "safaera", "guarachar", "guaracha", "morder", "labio", "cachonda"],
    "💑": ["pareja", "juntos", "contigo", "nuestra relacion", "tu y yo", "somos nosotros", "mios", "tuyo", "nuestra", "relacion"],
    "🫂": ["abrazo", "abrazame", "cerca de ti", "junto a ti"],
    "🌹": ["romantico", "romantica", "conquistar", "enamorar", "seducir", "seduccion", "flores para ella", "rosa roja"],
    "🫀": ["latido", "late", "corazon late", "pulso", "palpitar"],
    "💥": ["detono", "detonar", "detonarte", "explosion", "explotar", "explotarte", "exploto", "partir", "te parto", "explota", "bang", "impacto", "bombazo", "boom", "golpe", "rompe pista", "rompo", "romper", "romperte"],
    # ── FESTA / BALLO / BEVANDE / VICIOS ──
    "🥳": ["Partyseo", "fiesta", "festejo", "party", "antro", "after", "afterparty", "farra", "parrandear", "parranda", "reventon", "reventar", "pachanga", "bulla", "vacile", "vacilando", "vacila", "joseo", "josear", "gocen"],
    "💃": ["Guaracheo","baila", "bailar", "rumba", "bailando", "sandungueo", "sandunga", "mueve", "moviendo", "menea", "meneando", "tumbao", "afincar", "afinca", "pegao", "pegada", "saoco", "pista", "dance", "dancing", "jangueo", "janguear", "janguea", "janguiando", "salsa", "bachata"],
    "🎉": ["cumpleaños", "aniversario", "felicitacion", "feliz cumple", "celebracion", "navidad", "año nuevo", "fin de año"],
    "🎊": ["celebrar", "confeti", "festejar", "en celebracion"],
    "🎂": ["pastel", "torta", "cumple", "velas", "años", "edad", "cumplió", "cumplio"],
    "🪅": ["pinata", "golpear fiesta", "fiesta infantil", "carnaval"],
    "🥃": ["ron", "whisky", "whiskey", "shot", "tequila", "trago", "alcohol", "borracho", "borracha", "ebrio", "ebria", "cantina", "vaso", "bebiendo", "tomar", "tomando", "beber", "bebemos", "cantinero", "bartender", "open bar", "free bar"],
    "🍾": ["champagne", "champaña", "bottle", "botella", "descorchar", "moet", "hennessy", "cava", "espumante", "botella vip", "vip", "reservado", "table service", "brindis", "salud"],
    "🍻": ["cerveza", "chelas", "frias", "birra", "chelita", "birritas", "cervezas"],
    "🍷": ["copa", "vino", "tinto"],
    "🍹": ["jolly", "sprite", "cocacola", "coca cola", "trago dulce"],
    "🌿": ["yerba", "yelba", "mary", "maria", "marihuana", "pasto", "blunt", "blunts", "porro", "mota", "kush", "zaza", "hierba", "weed", "ganja", "420", "fumamos"],
    "💨": ["vapor", "fuma", "fumo", "fumando", "humo", "smoke", "smoking", "vape", "vapeo", "hookah", "pipa", "exhala", "gas", "nube humo", "bonga"],
    "🟣": ["lean", "codeina", "codeine", "jarabe", "syrup", "tuss", "morado", "actavis", "promethazine", "purp", "purple drank"],
    "💊": ["Plan B", "pastilla", "perco", "percocet", "molly", "mdma", "xan", "xanax", "tusi", "tussi", "pepa", "droga", "elevado", "elevada", "dosis", "oxy", "perco 30"],
    "🚬": ["cigarro", "cigarrillo", "tabaco", "swisher", "ceniza"],
    # ── EMOZIONI / ESPRESSIONI ──
    "🔥": ["fuego", "candela", "quema", "ardiente", "llamas", "fire", "hot", "prendido", "tremendo", "brutal", "duro", "dura", "heavy", "bestial", "lo maximo", "caliente", "encendido", "calor"],
    "😂": ["risa","ahah", "haha", "jaja", "jajaja", "reir", "riendo", "gracioso", "me rio", "muerto de risa", "muerta de risa", "lmao", "lol", "chiste", "broma", "burlar"],
    "😡": ["enojado", "enojada", "rabia", "coraje", "furia", "molesto", "odio", "ira", "fastidio", "me tiene harto", "me cae mal", "lo odio", "la odio", "molesta"],
    "🤬": ["hijo 'e puta","hijo de puta","jodido", "mierda", "maldito", "maldita", "carajo", "puñeta", "relajate", "diantre"],
    "🤯": ["increible", "sorpresa", "wow", "impresionante", "no lo puedo creer", "mente", "sorprendido", "sorprendida"],
    "😵": ["en coma", "coma", "inconsciente", "desmayado", "desmayada"],
    "😎": ["cool", "chevere", "bacano", "chido", "chulo",],
    "😏": ["Se te nota","picaro", "picara", "sugerente", "insinuando", "con malicia", "coqueto", "coqueta", "jodiendo", "provocando", "medio sonrisa"],
    "🤪": ["loco", "loca", "crazy", "demente", "chiflado", "salido", "salida", "descontrolado", "locura"],
    "😤": ["orgulloso", "orgullosa", "altivo", "presumiendo", "guillar", "guillandose", "fanfarron", "fronteando", "fronteo", "echando foco", "bufando", "resoplando"],
    "😩": ["desespera", "desesperado", "desesperados", "desesperada", "agobiado", "demoras"],
    "🥺": ["lo siento", "extraño", "perdon", "culpa", "vuelve", "regresa", "nostalgia", "recuerdo", "te extrano", "te extraño", "sin ti", "sentimientos"],
    "😢": ["llorar", "lagrimas", "llorando", "deprimido", "triste", "tristeza llanto", "llanto", "me rompe el alma", "depresion"],
    "😨": ["miedo", "susto", "asustado", "asustada", "asustar", "asusta", "temor", "panico", "terror", "tiembla", "pesadilla"],
    "🫣": ["cosas feas", "cosa fea", "vergüenza", "timido", "escondido", "pena ajena", "me escondo"],
    "😴": ["dormir", "duermo", "cansado", "cansada", "agotado", "siesta", "tras la noche", "nap"],
    "💤": ["sueño", "dormido", "dormida", "zzz"],
    "🤫": ["ching-","secreto", "callao", "silencio", "nadie sabe", "entre tu y yo", "privado", "confidencial", "shh", "calla", "mudo", "mucha bulla"],
    "🤔": ["pensar", "pensando", "reflexion", "dudando", "analizando", "me pregunto", "quizas", "creo que", "tal vez"],
    "💭": ["recordando", "recuerdos", "pensamiento", "pensando en ti"],
    "🔄": ["Otra", "ciclo ", "vírate", "virate", "vírate pa aca", "virate pa aca", "gírate", "girate", "date la vuelta", "volteate"],
    "🤭": ["risita", "tapando boca", "chisme", "secreto gracioso"],
    "😪": ["melancolico", "suspiro", "languidez", "lagrimita"],
    "🥴": ["mareado", "marea"],
    "🤩": ["fascinado", "fascinante", "deslumbrado", "emocionado", "emocion", "estrellas en ojos"],
    "🥹": ["aguantando", "lagrimas feliz", "emocionado llorar", "conmovido"],
    "😬": ["incomodo", "nervioso", "tenso", "awkward", "situacion rara"],
    "🥵": ["nena moxita", "en exceso","sudor", "sudando", "me derrito", "que calor", "sobrecalentado", "acalorado", "sofocao", "fiebre"],
    "😈": ["picky","Senda bellacona","zorra","atrevete","atrevida", "atravido","putilla","putona", "puta", "malo", "mala", "bad", "diablo", "diabla", "bandido", "bandida", "pecado", "portarse mal", "lado oscuro", "maldad", "villano", "villana", "mala influencia", "peligroso", "peligrosa", "tiguere", "tiguera", "malandro", "malandreo", "cabron", "cabrona", "infierno", "lucifer"],
    "😇": ["angel", "pura", "puro", "inocente", "santa", "santo", "buena gente", "sin maldad", "limpia", "limpio", "bueno", "buena", "portarse bien", "juiciosa", "juicioso"],
    # ── STATUS / POTERE / SUCCESSO ──
    "👑": ["rey", "reina", "jefe", "jefa", "patron", "capo", "corona", "lider", "dueño", "dueña", "manda", "empire", "imperio", "cangri", "el mas duro", "la mas dura", "numero uno", "el jefe", "la jefa", "big boss", "poder"],
    "💅": ["chicha'", "bichota", "diva", "reina mia", "potra", "independiente", "fina", "carisima", "arreglada", "maquillaje", "unas", "bella", "hermosa", "bonita", "linda", "guapa", "mujer poderosa", "empoderamiento", "self love", "me amo", "me quiero", "nena fina", "nena' fina"],
    "🏆": ["campeon", "campeonas", "trofeo", "ganador", "ganar", "gano", "victoria", "vencedor", "titulo", "el mejor", "la mejor", "goat", "leyenda", "legendary", "historico", "premio"],
    "🐐": ["cabra", "greatest", "mejor de todos", "ninguno como yo", "imbatible", "invicto", "sin rival", "mejor"],
    "🎖️": ["medalla", "honor", "merecido", "logro", "consegui"],
    "🫡": ["respeto", "a sus ordenes", "el jefazo manda", "saludo", "con respeto", "saludo militar", "jefazo"],
    "💯": ["al cien", "cien por ciento", "real", "autentico", "genuino", "de verdad", "no fake", "sincero", "cien", "ciento", "hundred"],
    "🔝": ["top"],
    # ── DENARO / LUSSO / BUSINESS ──
    "💰": ["dinero", "money", "paca", "guita", "billetes", "efectivo", "millones", "millon", "riqueza", "cash", "chavos", "chavitos", "pasta", "lana", "feria", "cuartos", "billete'","billete", "pan", "bread", "cuenta millonaria", "dolares", "euros", "mucho dinero", "contando billete", "contando dinero", "plata", "bichote", "bichote'"],
    "💸": ["gasto", "gastar", "pago", "pagar", "compro", "comprar", "derrochar", "caro", "lujo", "precio alto", "designer", "gucci", "lv", "balenciaga", "versace", "dior", "prada", "fendi", "hermes", "shopping", "compras lujosas", "las paca' de cien", "las pacas"],
    "⚠️": ["el motin", "el motín", "motin", "motín", "alerta", "peligro"],
    "💎": ["diamante", "diamantes", "joya", "joyas", "vvs", "vvs1", "vvs2", "cadena", "anillo", "oro", "plata joya", "quilates", "bling", "blin blin", "brillantes", "ice", "iced out", "jacob", "richard mille", "audemars", "ap", "rolex"],
    "💳": ["tarjeta", "credito", "debito", "visa", "mastercard", "compras"],
    "🏦": ["banco", "inversion", "capital", "fondos", "cuenta bancaria", "deposito"],
    "📈": ["sube", "subiendo", "crecimiento", "alza", "mas alto", "ascender", "level up", "up"],
    "📉": ["baja", "perdida", "caida", "desplome"],
    # ── MUSICA / SPETTACOLO ──
    "🎤": ["microfono escena", "show", "concierto", "presentacion", "freestyle", "rap", "rapear", "tirar bars", "bars", "rimas", "rimar", "rimo", "en el escenario", "stage", "flow", "mic"],
    "🎙": ["estudio", "en el estudio", "canto", "canta", "cantar", "voz", "acapella", "vocal", "coro", "chorus", "grabacion", "sesion", "session", "cabina", "microfono"],
    "🎵": ["musica", "nota musical", "ritmo", "melodia", "tono musical", "instrumento", "beat", "pista musical", "cancion", "nota"],
    "🎶": ["canciones", "playlist", "album", "tema", "track", "hit", "hits", "sencillo", "nuevo tema", "nueva cancion", "estreno"],
    "🎧": ["dj", "mezcla", "mix", "productor", "produccion", "beats", "remix"],
    "🪩": ["La Placita","discoteca", "disco", "club", "espejo bola", "en la pista",],
    "🎹": ["piano", "teclas", "productor musical", "produccion musical", "componer", "compositor"],
    "🥁": ["bateria", "tambor", "percusion", "bombo", "tarola"],
    "🎸": ["guitarra", "acustica", "electrica", "riff", "rock"],
    "🎺": ["trompeta", "merengue", "orquesta", "banda", "cumbia", "vallenato", "metales"],
    "🎻": ["violin", "cuerdas", "clasico", "romantico instrumental"],
    # ── MEDIA / TECNOLOGIA / GIOCHI ──
    "🎥": ["video", "clip", "videoclip", "youtube", "camara", "grabando video", "grabame","graba", "filmando", "director", "grabar", "grabando", "rec", "pelicula", "cine", "tiktok"],
    "📸": ["foto", "fotografia", "paparazzi", "pose", "flash camara", "lente", "photoshoot", "picture", "retrato", "say cheese"],
    "🤳": ["selfie", "selfie cam", "selfie time"],
    "📱": ["call","telefono", "celular","celulares", "movil", "phone", "iphone", "llama", "llamar", "llamada", "mensaje", "dm", "whatsapp", "texto", "story", "stories", "instagram", "pantalla", "notificacion"],
    "📲": ["texteé", "textee", "textear", "texteame"],
    "📺": ["television", "tele", "canal", "programa", "serie", "novela"],
    "🔴": ["live","en vivo", "directo", "streaming", "en el aire", "en_vivo"],
    "🎮": ["videojuego", "juego", "gamer","gameplay"],
    "🃏": ["carta", "cartas", "poker", "blackjack", "casino", ],
    "🎰": ["tragamonedas", "casino apostar", "suerte", "azar", "apostar", "apuesta"],
    "🎲": ["azar dados", "suerte dados", "dados", "roll the dice"],
    "🎭": ["teatro", "mascara", "actuando", "fake show", "posando", "fingiendo", "drama", "obra"],
    "💻": ["computadora", "laptop", "pc", "hackear", "programar", "ordenador", "pantalla trabajo"],
    "⌨️": ["teclear", "escribir", "codigo tecla", "programacion"],
    "🖥️": ["monitor", "escritorio", "setup", "estudio casero"],
    # ── VEICOLI / TRASPORTO ──
    "🚗": ["carro", "v6", "v8", "v10", "v12", "coche", "nave", "motor", "acelerar", "velocidad", "ferrari", "AMG", "benz", "mercedes", "lambo", "lamborghini", "porsche", "maserati", "bentley", "rolls royce", "maybach", "bugatti", "manejar", "corriendo en el carro", "audi", "honda"],
    "🏍️": ["moto", "motocicleta", "motos", "ruedas dos", "bike", "biker", "encima la moto", "motosicleta", "motora", "motorita", "en la motora", "rodando en moto"],
    "✈️": ["avion", "vuelo", "aeropuerto", "pasaporte", "viaje", "viajar", "volando naciones", "private jet", "jet privado", "turista", "primera clase", "first class", "business class", "frontera"],
    "🚁": ["helicoptero", "chopper", "helicoptero privado"],
    "🚤": ["yacht", "yate", "lancha", "barco", "mar", "oceano", "al bote", "en el bote", "andar en bote"],
    "🛣️": ["calle","carretera", "autopista", "via", "en la carretera"],
    "🚂": ["tren", "locomotora", "via ferrea"],
    "🚲": ["bici", "bicicleta", "pedales", "ciclista"],
    "⛵": ["velero", "vela", "navegando", "navegacion"],
    "🚀": ["despegar", "lanzamiento", "rocket", "go up", "al infinito", "subiendo rapido", "cohete", "espacio"],
    "🛸": ["nave espacial", "ufo", "ciencia ficcion"],
    "🏃": ["corro", "corriendo", "fugarse", "escapar", "lejos", "huir", "perseguir", "correr"],
    # ── STRADA / PERICOLO / VIOLENZA ──
    "🏚️": ["barrio", "caserio", "bloque", "callejon", "ghetto", "hood", "esquina", "pata en el suelo", "humilde origen", "bando", "zona"],
    "🔫": ["dispara", "plomo", "pistola", "arma", "armas", "bala", "glock", "glock 17", "draco", "ak", "ak47", "ak 47", "calibre", "gatillo", "disparo", "tiro", "shooting", "matar", "delincuente","gangster", "ga" "criminal", "criminales", "crimen", "sicario", "maleante", "pandillero", "pandilleros", "banda criminal", "glopeta", "escopeta", "pow pow"],
    "💣": ["bomba", "guerra", "estallar", "peligro"],
    "⚔️": ["batalla", "combate", "guerrero", "rival", "enemigo", "tiraera", "diss", "war", "lucha"],
    "🗡️": ["navaja", "filo", "punta", "acero frio", "cuchillo"],
    "🧨": ["petardo", "fuego artificial", "celebrar con ruido", "chispa"],
    "⚰️": ["entierro", "ataud", "velorio", "funeral", "sepelio"],
    "🔒": ["encerrado", "prision", "carcel", "jaula", "preso", "bajo llave", "cayo preso", "adentro", "detenido", "cerrado"],
    "🔓": ["libre", "liberado", "soltar", "soltaron", "salio", "me fui libre", "en libertad", "escapo", "abriendo"],
    "🚓": ["policia", "patrulla", "jura", "ley", "fuerza del orden", "arresto", "me busca la policia", "perseguido", "sirena"],
    "🛑": ["stop", "basta", "para", "frena", "detente", "no mas", "se acabo", "punto final", "limite", "frenar"],
    # ── TRADIMENTO / INSULTI ──
    "🐍": ["serpiente", "traicion", "vibora", "snake", "traicionero", "te clavan por la espalda", "venenosa"],
    "🐀": ["rata", "chivato", "soplon", "traidor", "informante", "lengua larga", "corrio la boca",],
    "🤡": ["payaso", "bobo", "pendejo", "tonto", "idiota", "ridiculizado", "falso", "fake", "clown", "estupido", "ridiculo"],
    "🖕": ["jodete", "pudrete","fuck you"],
    "❌": ["no", "nunca", "jamas", "nadie", "nada", "prohibido", "error", "equivocado", "negativo"],
    # ── GESTI / MANI ──
    "🙏": ["rezo", "oracion", "dios", "gracias dios", "bendicion", "bendito", "dios mio", "senor", "por favor dios", "fe", "confia en dios", "ruego", "ora", "damelo", "dámelo"],
    "🤙": ["llamame", "tranquilo", "sin drama", "todo bien", "shaka", "dime", "llamado"],
    "🤏": ["poquito", "poquita", "un poquito", "poquitito"],
    "🙇‍♀️": ["en 4", "arrodilla", "arrodillate", "arrodillada", "de rodillas"],
    "👏": ["aplauso", "aplaudir", "que bien", "felicitaciones"],
    "🫶": ["te apoyo", "contigo siempre", "amor y apoyo", "solidaridad", "familia", "corazon manos"],
    "👯": ["amica'", "amigas", "bestie", "besties"],
    "🤷🏻‍♂️": ["Qué pasaría","no se", "No Sé","porque", "por que", "duda", "pregunta", "quien"],
    # ── CORPO / SENSI ──
    "👀": ["ve'", "mira","vea", "mirar", "te miro", "mirando", "te veo", "ojos encima", "todos te miran", "ojos", "observar", "vista", "ojo", "ver", "viendo", "ciego", "ve'"],
    "👂": ["escucha", "escuchar", "escuchando", "escuchame", "escucho", "oido", "oreja", "oyendo"],
    "🍑": ["perreo", "perrear","perreame", "perrearte", "twerk", "perrea","culo", "culito", "chapa", "nalgota", "nalgas","nalga'", "booty", "cadera", "curvas", "bien formada", "cuerpazo"],
    "🍒": ["implante'","tetota", "tetotas", "boobies", "boobie", "pecho", "pechos", "seno", "senos", "chichis", "teta", "teta'"],
    "🍆": ["bicho", "eggplant", "verga", "pinga", "miembro", "dicky"],
    "💪": ["musculo", "fuerza", "gym", "entreno", "entrenando", "fuerte", "pesa", "jangueo gym", "fitness"],
    "🦵": ["pierna", "piernas", "patea", "patada", "correr rapido"],
    "🦶": ["pie", "pies", "descalzo"],
    "🚶🏻‍♂️": ["caminar", "a pie", "pasos", "caminando"],
    "🧠": ["cerebro", "inteligente", "inteligencia", "listo", "lista", "pensamiento", "mente brillante", "estrategia", "calculo"],
    "🪞": ["espejo", "reflejo", "me miro", "narcisismo", "vanidad", "presencia", "narcisista"],
    "👅": ["mama", "mamame", "lamberte", "mamarte", "lenguetazo", "darte lengua", "chupa", "chuparte","chupo"],
    # ── OGGETTI / SIMBOLI ──
    "💡": ["idea", "se me ocurrio", "iluminacion", "eureka", "ocurrencia", "bombilla"],
    "🎯": ["objetivo", "meta", "acertar", "punteria", "apuntar", "diana", "al blanco", "on target"],
    "🗝️": ["llave", "clave", "la clave es", "secreto del exito", "acceso", "contraseña", "codigo", "abrir", "llave maestra"],
    "🧲": ["atraer", "atraccion", "imantado", "magnetico"],
    "♻️": ["reciclo", "reciclar", "reciclaje"],
    "🔮": ["predecir", "futuro", "adivina", "clarividente", "lo se todo", "bola cristal"],
    "📝": ["papeles", "contrato", "firmar contrato", "deal"],
    "📦": ["paquete", "caja", "envio", "delivery", "llegó", "paquete llego"],
    "⌚️": ["reloj", "tiempo", "hora", "minuto", "tarde", "temprano", "espera", "watch"],
    "⏱️": ["raitito", "ratito", "un ratito", "momentito"],
    "💍": ["sortija", "compromiso", "matrimonio", "casarse", "propuesta", "te caso", "pandora"],
    "📍": ["piercing", "arete", "stud", "punto marcado", "la meta"],
    "🩺": ["doctora", "doctor", "medico", "medica", "estetoscopio"],
    "📚": ["estudiosa", "estudioso", "libros"],
    "📅": ["agosto", "calendario", "fecha", "agenda"],
    "🚪": ["clóset", "closet", "armario", "guardarropa"],
    "🛡️": ["condón", "condon", "proteccion", "preservativo"],
    "🪟": ["balcón", "balcon", "ventana", "ventanal"],
    "🏬": ["mall", "centro comercial", "plaza", "shopping mall"],
    # ── ABBIGLIAMENTO / ACCESSORI ──
    "🏠": ["casa", "hogar", "vivienda", "residencia", "domicilio", "habitación", "habitacion", "cuarto", "piso", "departamento", "home", "penthouse"],
    "🛏️": ["cama", "en la cama", "acostado", "acostada", "sabanas", "almohada", "dormitorio", "en la habitacion"],
    "🛋️": ["la sala", "sala", "sillon", "sofá", "sofa", "living"],
    "🛁": ["bano", "baño", "banera", "bañera", "ducha"],
    "👶": ["bebé","baby", "bebecito", "bebecita", "nene", "nené", "nena"],
    "💇🏻‍♀️": ["beauty", "salon", "salon de belleza", "peinado", "estilista"],
    "👩": ["morena", "rubia", "peli roja", "pelirroja", "chica", "muchacha"],
    "👖": ["pantalon", "pantalones", "mahon", "jean", "jeans", "denim"],
    "👓": ["gafas", "lentes oscuros", "rayban", "oscuros", "sunglasses", "lentes", "oculares"],
    "👗": ["vestido", "ropa elegante", "outfit", "look", "bien vestida", "traje"],
    "👠": ["tacon", "zapatos altos", "stiletto", "heels", "de tacon", "tacones", "los taco'"],
    "👟": ["tenis", "sneakers", "zapatillas", "jordan", "nike", "adidas", "yeezy", "flow calle", "jordans", "air jordan"],
    "🧢": ["gorra", "gorro", "cap", "snapback", "fitted", "hat"],
    "👙": ["panties", "panti", "panty", "bikini", "playa ropa", "bañador", "traje baño","ropa interior"],
    "🧸": ["muneca", "muñeca", "barbie", "bambola"],
    "👜": ["vuitton", "louis vuitton", "bolso", "cartera"],
    # ── NATURA / CLIMA ──
    "🌴": ["palmera", "tropical", "caribe", "isla", "vacaciones", "paraiso", "playa tropical", "resort", "cancun", "punta cana", "miami beach", "riviera", "sunny"],
    "🌊": ["playa", "arena", "costa", "orilla", "surf", "olas", "ola", "beach", "seaside", "beachside"],
    "☀️": ["sol", "dia", "amanecer", "mañana", "luz", "verano", "soleado", "sunshine", "rayos de sol"],
    "🌙": ["luna", "noche", "madrugada", "nocturno", "night", "trasnochando", "de noche", "a las 3am", "en la noche", "de madrugada", "moonlight", "oscuro", "eclipse"],
    "✨": ["brillo", "brillar", "shining", "glowing", "glow up", "resplandor", "destello", "radiante", "magia", "aura"],
    "⭐️": ["estrella", "estrellas", "star", "superstar", "brilla como estrella", "fugaz", "constelacion"],
    "⚡": ["flash", "rayo", "electrico"],
    "🌧️": ["lluvia", "llover", "tormenta", "aguacero", "bajo la lluvia", "trueno"],
    "💧": ["gota", "agua"],
    "💦": ["moja'", "mojado", "mojaido"],
    "😋": ["lamber", "mamar", "chupar", "lamberte", "mamarte","chuparte" ],
    "🤤": ["que rico", "qué rico", "que rica", "qué rica", "antojado", "antojada"],
    "❄️": ["frio", "congelado", "fresco", "ice cold", "nieve", "nevar", "invierno", "frio extremo"],
    "🧊": ["hielo", "cubo", "rocas", "on the rocks", "iced"],
    "🥶": ["brrr", "brr", "congelando", "helando", "que frio"],
    "🌈": ["arcoiris", "colores", "colorido", "pride", "diversidad", "arco iris"],
    "☁️": ["nube", "cielo", "volar", "volando", "flotando", "alto"],
    "🌺": ["flor", "flores", "rosa", "rosas", "petal", "jardin", "primavera"],
    "🌵": ["desierto", "cactus", "seco", "vacio"],
    "🍃": ["hoja", "hojas", "naturaleza", "campo", "arbol"],
    # ── SPAZIO / COSMO ──
    "☄️": ["cometa", "asteroide", "meteoro", "meteorito"],
    "🪐": ["planeta", "saturno", "jupiter", "galaxia", "universo", "cosmos"],
    "🌌": ["galactic", "galactico", "via lactea", "milky way"],
    "👽": ["alien", "extraterrestre", "marciano", "ovni", "abduccion"],
    "👻": ["si no nos dejamo' ver", "no nos dejamo' ver", "escondidos", "fantasma"],
    # ── SPORT / FITNESS ──
    "🏋️": ["pesas", "levantamiento", "fuerza gym", "entreno pesado"],
    "🥊": ["boxeo", "pelea boxeo", "guantes", "ring", "knockout", "ko", "boxer", "pelea", "pelear", "peleamos", "peleando"],
    "⚽": ["futbol", "soccer", "gol", "pelota", "balon"],
    "🏀": ["basketball", "basquet", "canasta", "aro", "nba"],
    "🏊": ["nadar", "nadando", "piscina", "natacion"],
    "🏄": ["surfear", "surfer", "tabla surf", "ola surfear"],
    "🤸": ["acrobacia","de goma", "flexible", "gimnasia", "salto"],
    "🎿": ["esqui", "nieve esqui", "montana nieve"],
    "🏇": ["caballo", "carrera caballos", "hipodromo", "jinete"],
    # ── ANIMALI ──
    "🦁": ["animal","Leónidas","leon", "leona", "rugido", "fiero", "rey de la selva", "fiera", "safari"],
    "🦅": ["aguila", "volar alto", "libertad", "alto vuelo", "aguila real", "cumbre"],
    "🦋": ["mariposa", "transformacion", "nueva vida", "cambio", "evolucionar", "glow up cambio", "alas"],
    "🐝": ["abeja", "miel", "abeja reina", "productiva", "productivo", "trabajadora"],
    "🐈": ["miao","miaw", "gata", "gato", "gatita", "gatito", "felina", "michi", "leona felina", "gata'"],
    "🐶": ["perro", "perra", "cachorro", "bau"],
    "🐯": ["tigre", "tigresa", "feroz", "salvaje", "cazador"],
    "🦊": ["zorro", "astuto", "manipulador"],
    "🐺": ["lobo", "manada", "solitario", "feroz salvaje"],
    "🦈": ["tiburon", "acecho", "depredador"],
    "🐉": ["dragon", "fuego dragon", "leyenda bestia", "poder bestia"],
    "🦄": ["unicornio", "magico", "especial", "unico", "extraordinario"],
    "🐸": ["sapo", "rana", "saltando"],
    "🐇": ["conejo", "bunny"],
    # ── CIBO ──
    "🍔": ["hamburguesa", "burger", "comida", "hambre"],
    "🌮": ["taco", "tacos"],
    "🍫": ["chocolate", "dulce", "cacao", "bombon"],
    "🍬": ["caramelo", "chicle", "gomita", "azucar"],
    "🍭": ["lollipop", "paleta dulce"],
    "☕️": ["cafe", "cafecito", "desayuno", "despertar"],
    "🍕": ["pizza", "queso derretido", "pepperoni", "slice"],
    "🍜": ["ramen", "sopa", "tallarines", "fideos"],
    "🌯": ["burritos", "wrap", "enrollado", "comida latina"],
    "🍗": ["pollo", "pechuga", "muslo", "fried chicken", "frito"],
    "🥩": ["carne", "bistec", "asado", "parrilla", "bbq", "churrasco"],
    "🍣": ["sushi", "rollo", "atun"],
    "🍓": ["fresa", "dulce fruta", "rico", "delicioso"],
    "🍉": ["sandia", "verano fruta", "refrescante"],
    "🍇": ["uvas", "vino fruta", "racimo"],
    "🥝": ["kiwi", "exotico", "tropical fruta"],
    "🍦": ["helado", "nieve dulce", "cono", "paleta"],
    # ── BANDIERE / PAESI ──
    "🌍": ["mundo", "tierra", "global", "planeta tierra", "internacional"],
    "🇵🇷": ["puerto_rico", "pr", "boricua", "borinquen", "san juan", "bayamon", "carolina"],
    "🇨🇴": ["colombia", "parcero", "parcera", "medellin", "Medellín", "bogota", "colombiano", "colombiana", "paisa", "cali"],
    "🇲🇽": ["mexico", "mexicano", "mexicana", "cdmx", "monterrey", "guadalajara"],
    "🇦🇷": ["argentina", "argentino", "buenos aires", "che", "pibe"],
    "🇩🇴": ["republica_dominicana", "dominicano", "rd", "dembow", "tigere", "santo domingo", "R.D."],
    "🇪🇸": ["españa", "español", "madrid", "barcelona", "ibiza"],
    "🇺🇸": ["usa", "estados unidos", "gringo", "gringa", "miami", "nueva york", "los angeles", "ny"],
    "🇮🇹": ["italia", "italiano", "roma", "milano"],
    "🇧🇷": ["brasil", "brasileño", "brasileña", "rio", "sao paulo", "carioca"],
    "🇻🇪": ["venezuela", "venezolano", "venezolana", "caracas", "maracaibo", "llanero"],
    "🇵🇦": ["panama", "panameño", "panameña", "ciudad de panama", "canalero"],
    "🇨🇺": ["cuba", "cubano", "cubana", "habana", "la habana", "habanero"],
    "🇵🇪": ["peru", "peruano", "peruana", "lima", "cusco"],
    "🇨🇱": ["chile", "chileno", "chilena", "santiago"],
    "🇯🇲": ["jamaica", "jamaicano", "reggae", "rasta", "kingston"],
    "🇵🇹": ["portugal", "portugues", "portuguesa", "lisboa",],
    "🇫🇷": ["francia", "frances", "francesa", "paris", "lyon"],
    "🇩🇪": ["alemania", "aleman", "alemana", "berlin"],
    "🇬🇧": ["reino unido", "ingles uk", "london", "londres"],
    "🇯🇵": ["japon", "japones", "japonesa", "tokio", "anime"],
    # ── NUMERI ──
    "0️⃣": ["cero", "zero", "0"],
    "1️⃣": ["uno", "one", "primero", "1"],
    "2️⃣": ["dos", "two", "segundo", "2"],
    "3️⃣": ["tres", "three", "tercero", "3"],
    "4️⃣": ["cuatro", "four", "4"],
    "5️⃣": ["cinco", "five", "5"],
    "6️⃣": ["seis", "six", "6"],
    "7️⃣": ["siete", "seven", "7"],
    "8️⃣": ["ocho", "eight", "8"],
    "9️⃣": ["nueve", "nine", "9"],
    "🔟": ["diez", "ten", "10", "die'"],
    "1️⃣1️⃣": ["once", "11"],
    "1️⃣2️⃣": ["doce", "12"],
    "1️⃣3️⃣": ["trece", "13"],
    "1️⃣4️⃣": ["catorce", "14"],
    "1️⃣5️⃣": ["quince", "15"],
    "2️⃣0️⃣": ["veinte", "20"],
    "2️⃣1️⃣": ["veintiuno", "21"],
}

FLAT_EMOJI_MAP = {}
for emoji, words in EMOJI_DICT.items():
    for word in words:
        FLAT_EMOJI_MAP[word] = emoji


def _normalize_for_match(text):
    # Normalize common apostrophe variants to avoid regex boundary misses (e.g. "moja'").
    text = re.sub(r"[\u2019\u2018\u0060\u00b4\u02bc']+", "", text)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.lower().strip()

_NON_ALNUM_RE = re.compile(r"[^a-z0-9 ]+")


def _tokenize_normalized(text):
    text = _NON_ALNUM_RE.sub(" ", text)
    return [tok for tok in text.split() if tok]


_KEYWORD_BY_FIRST = {}
_seen_keyword_pairs = set()
for _word, _emoji in FLAT_EMOJI_MAP.items():
    _word_norm = _normalize_for_match(_word.replace("_", " "))
    _tokens = tuple(_tokenize_normalized(_word_norm))
    if not _tokens:
        continue
    _pair_key = (_tokens, _emoji)
    if _pair_key in _seen_keyword_pairs:
        continue
    _seen_keyword_pairs.add(_pair_key)
    _KEYWORD_BY_FIRST.setdefault(_tokens[0], []).append((_tokens, _emoji))

for _first in _KEYWORD_BY_FIRST:
    _KEYWORD_BY_FIRST[_first].sort(key=lambda item: len(item[0]), reverse=True)

_NUMBER_RE = re.compile(r'\b\d+\b')
_DIGIT_MAP = {'0': '0️⃣', '1': '1️⃣', '2': '2️⃣', '3': '3️⃣', '4': '4️⃣',
              '5': '5️⃣', '6': '6️⃣', '7': '7️⃣', '8': '8️⃣', '9': '9️⃣'}
_DIGIT_EMOJIS = set(_DIGIT_MAP.values())
_HTTP_SESSION = requests.Session()
_HTTP_SESSION.headers.update({"User-Agent": "RayNeo/1.0"})
_HTTP_RETRY = Retry(
    total=2,
    connect=2,
    read=2,
    backoff_factor=0.25,
    status_forcelist=(429, 500, 502, 503, 504),
    allowed_methods=frozenset(["GET", "HEAD", "OPTIONS"]),
)
_HTTP_ADAPTER = HTTPAdapter(max_retries=_HTTP_RETRY, pool_connections=8, pool_maxsize=8)
_HTTP_SESSION.mount("https://", _HTTP_ADAPTER)
_HTTP_SESSION.mount("http://", _HTTP_ADAPTER)


def _safe_filename_token(text):
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = text.lower().replace("_", " ").strip()
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return text or "default"


EMOJI_FILENAME_MAP = {
    emoji: f"{_safe_filename_token(words[0])}.png"
    for emoji, words in EMOJI_DICT.items()
    if words
}


@lru_cache(maxsize=4096)
def _normalize_lookup_text(text):
    return _normalize_for_match(text)

NEGATION_TOKENS = frozenset(["no", "nunca", "jamas", "ni"])
MAX_EMOJI_EVENTS = 6


@lru_cache(maxsize=2048)
def _extract_emoji_events_cached(normalized_text):
    tokens = _tokenize_normalized(normalized_text)
    events = []

    def _has_match_at(start_idx):
        if start_idx >= len(tokens):
            return False
        for kw_tokens, _ in _KEYWORD_BY_FIRST.get(tokens[start_idx], []):
            k_len = len(kw_tokens)
            if tokens[start_idx:start_idx + k_len] == list(kw_tokens):
                return True
        return False

    i = 0
    while i < len(tokens) and len(events) < MAX_EMOJI_EVENTS:
        tk = tokens[i]

        # Keep numeric emoji support while preserving repeated occurrences.
        if tk.isdigit():
            combo = "".join(_DIGIT_MAP.get(d, "") for d in tk)
            if combo:
                events.append((combo, i, False))
                if len(events) >= MAX_EMOJI_EVENTS:
                    break

        matched = False
        for kw_tokens, emoji_to_add in _KEYWORD_BY_FIRST.get(tk, []):
            k_len = len(kw_tokens)
            if tokens[i:i + k_len] != list(kw_tokens):
                continue

            # "no <parola>" should mark the next emoji as negated instead of emitting standalone NO.
            if tk in NEGATION_TOKENS and emoji_to_add == "❌" and _has_match_at(i + k_len):
                matched = True
                i += k_len
                break

            negated = i > 0 and tokens[i - 1] in NEGATION_TOKENS
            center_idx = i + (k_len // 2)
            events.append((emoji_to_add, center_idx, negated))
            matched = True
            i += k_len
            break

        if not matched:
            i += 1

    return tuple(events[:MAX_EMOJI_EVENTS])


def extract_emoji_events(text):
    if not text:
        return []
    norm_text = _normalize_lookup_text(text)
    raw = _extract_emoji_events_cached(norm_text)
    return [
        {"emoji": emoji, "token_index": token_idx, "negated": negated}
        for emoji, token_idx, negated in raw
    ]


def extract_emojis(text):
    return [item["emoji"] for item in extract_emoji_events(text)]

def get_filename_for_emoji(emoji_char):
    return EMOJI_FILENAME_MAP.get(emoji_char, "default.png")

FLAG_EMOJI_CODEPOINTS = {
    "🇵🇷": "1f1f5-1f1f7",
    "🇨🇴": "1f1e8-1f1f4",
    "🇲🇽": "1f1f2-1f1fd",
    "🇦🇷": "1f1e6-1f1f7",
    "🇩🇴": "1f1e9-1f1f4",
    "🇪🇸": "1f1ea-1f1f8",
    "🇺🇸": "1f1fa-1f1f8",
    "🇮🇹": "1f1ee-1f1f9",
    "🇧🇷": "1f1e7-1f1f7",
    "🇻🇪": "1f1fb-1f1ea",
    "🇵🇦": "1f1f5-1f1e6",
    "🇨🇺": "1f1e8-1f1fa",
    "🇵🇪": "1f1f5-1f1ea",
    "🇨🇱": "1f1e8-1f1f1",
    "🇯🇲": "1f1ef-1f1f2",
    "🇵🇹": "1f1f5-1f1f9",
    "🇫🇷": "1f1eb-1f1f7",
    "🇩🇪": "1f1e9-1f1ea",
    "🇬🇧": "1f1ec-1f1e7",
    "🇯🇵": "1f1ef-1f1f5",
}

def download_flag_images(assets_dir):
    os.makedirs(assets_dir, exist_ok=True)
    ssl_blocked = False
    for emoji_char, codepoint in FLAG_EMOJI_CODEPOINTS.items():
        if ssl_blocked:
            break

        filename = get_filename_for_emoji(emoji_char)
        path = os.path.join(assets_dir, filename)
        if os.path.exists(path):
            continue

        legacy_path = os.path.join(assets_dir, filename.replace("_", " "))
        if os.path.exists(legacy_path):
            try:
                os.replace(legacy_path, path)
            except Exception:
                # Se il rename fallisce manteniamo il legacy come valido.
                pass
            if os.path.exists(path) or os.path.exists(legacy_path):
                continue

        url = f"https://cdn.jsdelivr.net/gh/jdecked/twemoji@latest/assets/72x72/{codepoint}.png"
        try:
            print(f"🏳️ Download bandiera: {filename}...")
            r = _HTTP_SESSION.get(url, timeout=10)
            if r.status_code == 200:
                with open(path, 'wb') as f:
                    f.write(r.content)
                print(f"   ✅ {filename} scaricato")
            else:
                print(f"   ⚠️ {filename} HTTP {r.status_code}")
        except Exception as e:
            print(f"   ⚠️ {filename} errore: {e}")
            if "CERTIFICATE_VERIFY_FAILED" in str(e):
                print("   ⚠️ Download bandiere interrotto: certificato SSL non verificabile")
                ssl_blocked = True
