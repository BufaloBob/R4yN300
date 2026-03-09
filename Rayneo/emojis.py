import re
import os
import requests
from functools import lru_cache

EMOJI_DICT = {
    # ── AMORE / ROMANTICISMO ──
    "❤️": ["corazon", "amor", "te amo", "te quiero", "enamorado", "enamorada", "amar", "cariño", "mi amor", "vida mia", "corazon mio", "mi vida", "novio", "novia", "esposa", "esposo", "bebe", "baby", "papi", "mami"],
    "❤️‍🔥": ["pasion", "loco por ti", "loca por ti", "obsesion", "obsesionado", "no te puedo olvidar", "me tienes loco", "me tienes loca", "fuego en el alma", "ardiendo por ti", "deseo loco"],
    "💔": ["roto", "desamor", "ex", "toxic", "toxica", "toxico", "dolor de amor", "herida", "traicion amor", "mentira", "engaño", "me fallo", "me falla", "te fuiste", "ya no estas", "me dejo", "me deja", "olvidame", "no te merecia", "fake love", "amor falso", "tristeza", "dolor", "murio", "murio amor", "morir", "se murio"],
    "💋": ["beso", "besos", "besito", "labios", "boca", "muah", "besar", "besame", "dame un beso", "labios rojos", "kiss", "kissing"],
    "🫦": ["sexy","sex", "sensual", "tentacion", "provocar", "bellaqueo", "bellaca", "bellaco", "ganas", "caliente de ganas", "cositas", "cosa rica", "cosas malas", "morbosa", "morboso", "picante", "safaera", "guarachar", "guaracha", "morder", "labio"],
    "💑": ["pareja", "juntos", "contigo", "nuestra relacion", "tu y yo", "somos nosotros", "mios", "tuyo", "nuestra", "relacion"],
    "💏": ["abrazo", "abrazame", "cerca de ti", "junto a ti", "piel con piel", "cerca", "piel"],
    "🌹": ["romantico", "romantica", "conquistar", "enamorar", "seducir", "seduccion", "flores para ella", "rosa roja"],
    "💐": ["ramo", "flores para ti", "regalo flores", "bouquet"],
    "🫀": ["latido", "late", "corazon late", "pulso", "palpitar"],
    # ── FESTA / BALLO / BEVANDE / VICIOS ──
    "🥳": ["fiesta", "festejo", "rumba", "party", "celebrar", "discoteca", "club", "antro", "after", "afterparty", "farra", "parrandear", "parranda", "reventon", "reventar", "pachanga", "bulla", "vacile", "vacilando", "vacila", "joseo", "josear", "gocen"],
    "💃": ["baila", "bailar", "bailando", "perreo", "perrear", "perrea", "sandungueo", "sandunga", "twerk", "mueve", "moviendo", "menea", "meneando", "tumbao", "afincar", "afinca", "pegao", "pegada", "saoco", "dembow", "pista", "dance", "dancing", "jangueo", "janguear", "janguea", "janguiando", "salsa", "bachata", "ritmo"],
    "🎉": ["cumpleaños", "aniversario", "felicitacion", "feliz cumple", "celebracion", "navidad", "año nuevo", "fin de año"],
    "🎊": ["confeti", "celebracion grande", "evento", "inauguracion"],
    "🎂": ["pastel", "torta", "cumple", "velas", "años", "edad"],
    "🪅": ["pinata", "golpear fiesta", "fiesta infantil", "carnaval"],
    "🥃": ["ron", "whisky", "whiskey", "shot", "tequila", "trago", "alcohol", "borracho", "borracha", "ebrio", "ebria", "cantina", "vaso", "bebiendo", "tomar", "tomando", "beber", "bebemos", "cantinero", "bartender", "open bar", "free bar"],
    "🍾": ["champagne", "champaña", "bottle", "botella", "descorchar", "moet", "hennessy", "cava", "espumante", "botella vip", "vip", "reservado", "table service", "brindis", "salud"],
    "🍻": ["cerveza", "chelas", "frias", "birra", "chelita", "birritas", "cervezas"],
    "🍷": ["copa", "vino", "tinto"],
    "🌿": ["yerba", "yelba", "mary", "maria", "marihuana", "pasto", "blunt", "blunts", "porro", "mota", "kush", "zaza", "hierba", "weed", "ganja", "420", "fumamos"],
    "💨": ["fuma", "fumo", "fumando", "humo", "smoke", "smoking", "vape", "vapeo", "hookah", "pipa", "exhala", "gas", "nube humo"],
    "🟣": ["lean", "codeina", "codeine", "jarabe", "syrup", "tuss", "morado", "actavis", "promethazine", "purp", "purple drank"],
    "💊": ["pastilla", "perco", "percocet", "molly", "mdma", "xan", "xanax", "tusi", "tussi", "pepa", "droga", "elevado", "elevada", "dosis", "oxy"],
    "🚬": ["cigarro", "cigarrillo", "tabaco", "swisher", "ceniza"],
    # ── EMOZIONI / ESPRESSIONI ──
    "🔥": ["fuego", "candela", "quema", "ardiente", "llamas", "fire", "hot", "prendido", "tremendo", "brutal", "duro", "dura", "heavy", "bestial", "lo maximo", "salvaje", "caliente", "encendido", "calor"],
    "😂": ["risa","ahah", "haha", "jaja", "jajaja", "reir", "riendo", "gracioso", "me rio", "muerto de risa", "muerta de risa", "lmao", "lol", "chiste", "broma", "burlar"],
    "😡": ["enojado", "enojada", "rabia", "coraje", "furia", "molesto", "odio", "ira", "fastidio", "me tiene harto", "me cae mal", "lo odio", "la odio", "molesta"],
    "🤬": ["puta", "jodido", "mierda", "maldito", "maldita", "carajo", "puñeta", "relajate", "diantre"],
    "🤯": ["increible", "sorpresa", "wow", "impresionante", "no lo puedo creer", "mente", "explotar", "sorprendido", "sorprendida"],
    "😎": ["cool", "chevere", "bacano", "chido", "fresco", "chulo",],
    "😏": ["picaro", "picara", "sugerente", "insinuando", "con malicia", "coqueto", "coqueta", "jodiendo", "provocando", "medio sonrisa"],
    "🤪": ["loco", "loca", "crazy", "demente", "chiflado", "salido", "salida", "descontrolado", "locura"],
    "😤": ["orgulloso", "orgullosa", "altivo", "presumiendo", "guillar", "guillandose", "fanfarron", "fronteando", "fronteo", "echando foco", "bufando", "resoplando"],
    "😩": ["desespera", "desesperado", "desesperados", "desesperada", "agobiado"],
    "🥺": ["lo siento", "extraño", "perdon", "culpa", "vuelve", "regresa", "nostalgia", "recuerdo", "te extrano", "te extraño", "sin ti", "sentimientos"],
    "😢": ["llorar", "lagrimas", "llorando", "deprimido", "triste", "tristeza llanto", "llanto", "me rompe el alma", "depresion"],
    "😨": ["miedo", "susto", "asustado", "asustada", "asustar", "asusta", "temor", "panico", "terror", "tiembla", "pesadilla"],
    "🫣": ["cosas feas", "cosa fea", "vergüenza", "timido", "escondido", "pena ajena", "me escondo"],
    "😴": ["dormir", "duermo", "sueño", "cansado", "cansada", "agotado", "siesta", "tras la noche", "nap"],
    "🤫": ["secreto", "callao", "silencio", "nadie sabe", "entre tu y yo", "privado", "confidencial", "shh", "calla", "escondido", "mudo"],
    "🤔": ["pensar", "pensando", "reflexion", "dudando", "analizando", "me pregunto", "quizas", "creo que", "tal vez"],
    "🤭": ["risita", "tapando boca", "chisme", "secreto gracioso"],
    "😪": ["melancolico", "suspiro", "languidez", "lagrimita"],
    "🥴": ["mareado", "confundido", "perdido", "borracho mental", "aturdido"],
    "🫠": ["derritiendo", "derrumbe", "perdiendo la forma", "fundiendo"],
    "🤩": ["fascinado", "fascinante", "deslumbrado", "emocionado", "emocion", "estrellas en ojos"],
    "🥹": ["aguantando", "lagrimas feliz", "emocionado llorar", "conmovido"],
    "😬": ["incomodo", "nervioso", "tenso", "awkward", "situacion rara"],
    "🥵": ["sudor", "sudando", "me derrito", "que calor", "sobrecalentado", "acalorado", "sofocao", "fiebre"],
    "😈": ["malo", "mala", "diablo", "diabla", "bandido", "bandida", "pecado", "portarse mal", "lado oscuro", "maldad", "villano", "villana", "mala influencia", "peligroso", "peligrosa", "tiguere", "tiguera", "malandro", "malandreo", "cabron", "cabrona", "infierno", "lucifer"],
    "😇": ["angel", "pura", "puro", "inocente", "santa", "santo", "cielo", "buena gente", "sin maldad", "limpia", "limpio", "bueno", "buena", "portarse bien", "juiciosa", "juicioso"],
    # ── STATUS / POTERE / SUCCESSO ──
    "👑": ["rey", "reina", "jefe", "patron", "capo", "corona", "lider", "dueño", "dueña", "manda", "empire", "imperio", "cangri", "el mas duro", "la mas dura", "numero uno", "el jefe", "la jefa", "big boss", "poder"],
    "💅": ["bichota", "diva", "reina mia", "potra", "independiente", "fina", "carisima", "arreglada", "maquillaje", "unas", "bella", "hermosa", "bonita", "linda", "guapa", "mujer poderosa", "empoderamiento", "self love", "me amo", "me quiero"],
    "🏆": ["campeon", "campeonas", "trofeo", "ganador", "ganar", "gano", "victoria", "vencedor", "titulo", "el mejor", "la mejor", "goat", "leyenda", "legendary", "historico", "premio"],
    "🐐": ["cabra", "greatest", "mejor de todos", "ninguno como yo", "imbatible", "invicto", "sin rival", "mejor"],
    "🎖️": ["medalla", "honor", "merecido", "logro", "consegui"],
    "🫡": ["respeto", "a sus ordenes", "el jefazo manda", "saludo", "con respeto", "saludo militar", "jefazo"],
    "💯": ["al cien", "cien por ciento", "real", "autentico", "genuino", "de verdad", "no fake", "sincero", "cien", "ciento", "hundred"],
    "🔝": ["top"],
    # ── DENARO / LUSSO / BUSINESS ──
    "💰": ["dinero", "money", "paca", "guita", "billetes", "efectivo", "millones", "millon", "riqueza", "cash", "chavos", "chavitos", "pasta", "lana", "feria", "cuartos", "billete", "pan", "bread", "cuenta millonaria", "dolares", "euros", "mucho dinero", "contando billete", "contando dinero", "plata"],
    "💸": ["gasto", "gastar", "pago", "pagar", "compro", "comprar", "derrochar", "caro", "lujo", "precio alto", "designer", "gucci", "louis vuitton", "lv", "balenciaga", "versace", "dior", "prada", "fendi", "hermes", "shopping", "compras lujosas"],
    "💎": ["diamante", "diamantes", "joya", "joyas", "vvs", "vvs1", "vvs2", "cadena", "anillo", "oro", "plata joya", "quilates", "bling", "blin blin", "brillantes", "ice", "iced out", "jacob", "richard mille", "audemars", "ap", "rolex"],
    "💳": ["tarjeta", "credito", "debito", "visa", "mastercard", "compras"],
    "🏦": ["banco", "inversion", "capital", "fondos", "cuenta bancaria", "deposito"],
    "📈": ["sube", "subiendo", "crecimiento", "alza", "mas alto", "ascender", "level up", "up"],
    "📉": ["baja", "perdida", "caida", "desplome"],
    # ── MUSICA / SPETTACOLO ──
    "🎤": ["microfono escena", "show", "concierto", "presentacion", "freestyle", "rap", "rapear", "tirar bars", "bars", "rimas", "rimar", "rimo", "en el escenario", "stage", "flow", "mic"],
    "🎙": ["estudio", "grabando", "en el estudio", "canto", "canta", "cantar", "voz", "acapella", "vocal", "coro", "chorus", "grabacion", "sesion", "session", "cabina", "microfono"],
    "🎵": ["musica", "nota musical", "ritmo", "melodia", "tono musical", "instrumento", "beat", "pista musical", "cancion", "nota"],
    "🎶": ["canciones", "playlist", "album", "disco", "tema", "track", "hit", "hits", "sencillo", "lanzamiento", "nuevo tema", "nueva cancion", "estreno"],
    "🎧": ["audifonos", "auriculares", "dj", "mezcla", "mix", "productor", "produccion", "beats", "escuchando"],
    "🎹": ["piano", "teclas", "productor musical", "produccion musical", "componer", "compositor"],
    "🥁": ["bateria", "tambor", "percusion", "bombo", "caja", "tarola"],
    "🎸": ["guitarra", "acustica", "electrica", "riff", "rock"],
    "🎺": ["trompeta", "salsa", "merengue", "orquesta", "banda", "cumbia", "vallenato", "metales"],
    "🎻": ["violin", "cuerdas", "clasico", "romantico instrumental"],
    # ── MEDIA / TECNOLOGIA / GIOCHI ──
    "🎥": ["video", "clip", "videoclip", "youtube", "camara", "grabando video", "grabame","graba", "filmando", "director", "grabar", "grabando", "rec", "pelicula", "cine", "tiktok"],
    "📸": ["foto", "fotografia", "selfie", "paparazzi", "pose", "flash camara", "lente", "photoshoot", "picture", "retrato"],
    "📱": ["telefono", "celular","celulares", "movil", "phone", "iphone", "llama", "llamar", "llamada", "mensaje", "dm", "whatsapp", "texto", "story", "stories", "instagram", "pantalla", "notificacion"],
    "📺": ["television", "tele", "canal", "programa", "serie", "novela"],
    "🔴": ["live","en vivo", "live", "directo", "streaming", "en el aire", "en_vivo"],
    "🎮": ["videojuego", "juego", "gamer","gameplay"],
    "🃏": ["carta", "cartas", "poker", "blackjack", "casino", ],
    "🎰": ["tragamonedas", "casino apostar", "suerte", "azar", "apostar", "apuesta"],
    "🎲": ["azar dados", "suerte dados", "dados", "roll the dice"],
    "🎭": ["teatro", "mascara", "actuando", "fake show", "posando", "fingiendo", "drama", "obra"],
    "💻": ["computadora", "laptop", "pc", "hackear", "programar", "codigo", "ordenador", "pantalla trabajo"],
    "⌨️": ["teclear", "escribir", "codigo tecla", "programacion"],
    "🖥️": ["monitor", "escritorio", "setup", "estudio casero"],
    # ── VEICOLI / TRASPORTO ──
    "🚗": ["carro", "v6", "v8", "v10", "v12", "coche", "nave", "motor", "acelerar", "velocidad", "ferrari", "lambo", "lamborghini", "porsche", "maserati", "bentley", "rolls royce", "maybach", "bugatti", "manejar", "corriendo en el carro", "carrera"],
    "🏍️": ["moto", "motocicleta", "motos", "ruedas dos", "bike", "biker", "encima la moto", "motosicleta"],
    "✈️": ["avion", "vuelo", "aeropuerto", "pasaporte", "viaje", "viajar", "volando naciones", "private jet", "jet privado", "turista", "primera clase", "first class", "business class", "frontera"],
    "🚁": ["helicoptero", "chopper", "helicoptero privado"],
    "🚤": ["yate", "lancha", "barco", "mar", "oceano"],
    "🚂": ["tren", "locomotora", "via ferrea"],
    "🚲": ["bici", "bicicleta", "pedales", "ciclista"],
    "⛵": ["velero", "vela", "navegando", "navegacion"],
    "🚀": ["despegar", "lanzamiento", "rocket", "go up", "al infinito", "subiendo rapido", "cohete", "espacio"],
    "🛸": ["nave espacial", "ufo", "ciencia ficcion"],
    "🏃": ["corro", "corriendo", "fugarse", "escapar", "lejos", "huir", "perseguir", "correr"],
    # ── STRADA / PERICOLO / VIOLENZA ──
    "🏚": ["barrio", "caserio", "bloque", "callejon", "ghetto", "hood", "calle", "esquina", "donde crei", "donde me crie", "de abajo", "de los bajos", "de la loma", "del caño", "de la calle", "pata en el suelo", "humilde origen", "bando", "zona"],
    "🔫": ["dispara", "plomo", "pistola", "arma", "armas", "bala", "glock", "glock 17", "draco", "ak", "ak47", "ak 47", "nine", "calibre", "gatillo", "disparo", "tiro", "shooting", "matar", "delincuente", "criminal", "criminales", "crimen", "sicario", "maleante", "pandillero", "pandilleros", "banda criminal", "glopeta", "escopeta", "pow pow"],
    "💣": ["bomba", "guerra", "explota", "estallar", "peligro"],
    "⚔️": ["batalla", "combate", "guerrero", "rival", "enemigo", "tiraera", "diss", "beef musical", "war", "pelea", "lucha"],
    "🗡️": ["navaja", "filo", "punta", "acero frio", "cuchillo"],
    "🪤": ["trampa", "emboscada", "me tendieron", "setup", "caer en trampa", "atrapar"],
    "🧨": ["petardo", "fuego artificial", "celebrar con ruido", "chispa"],
    "🪓": ["hacha", "cortar", "destruir", "romper todo"],
    "🔒": ["encerrado", "prision", "carcel", "jaula", "preso", "bajo llave", "cayo preso", "adentro", "detenido", "cerrado"],
    "🔓": ["libre", "liberado", "soltar", "soltaron", "salio", "me fui libre", "en libertad", "escapo", "abriendo"],
    "🚓": ["policia", "patrulla", "jura", "ley", "fuerza del orden", "arresto", "me busca la policia", "perseguido", "sirena"],
    "🛑": ["stop", "basta", "para", "alto", "frena", "detente", "no mas", "se acabo", "punto final", "limite", "frenar"],
    # ── TRADIMENTO / INSULTI ──
    "🐍": ["serpiente", "traicion", "vibora", "falso amigo", "snake", "traicionero", "te clavan por la espalda", "venenosa"],
    "🐀": ["rata", "sapo", "chivato", "soplon", "traidor", "informante", "lengua larga", "corrio la boca", "chisme"],
    "🤡": ["payaso", "bobo", "pendejo", "tonto", "idiota", "ridiculizado", "falso", "fake", "clown", "estupido", "ridiculo"],
    "🖕": ["jodete", "pudrete", "olvidame"],
    "❌": ["no", "nunca", "jamas", "nadie", "nada", "prohibido", "error", "equivocado", "negativo"],
    # ── GESTI / MANI ──
    "🙏": ["rezo", "oracion", "dios", "gracias dios", "bendicion", "bendito", "dios mio", "senor", "por favor dios", "fe", "confia en dios", "ruego", "ora"],
    "🤙": ["llamame", "tranquilo", "sin drama", "todo bien", "shaka", "dime", "llamado"],
    "👊": ["puño", "choque puños", "fuerza hermano", "respeto mutuo", "papow", "golpear"],
    "🤝": ["acuerdo", "trato", "alianza", "colaboracion", "pacto", "juntos en esto", "equipo", "respeto mutuo"],
    "✌️": ["paz", "libre", "peace", "victoria dedos", "two"],
    "🙌": ["palmas", "bendicion", "amen", "manos arriba", "manos", "celebrar"],
    "👏": ["aplauso", "aplaudir", "que bien", "felicitaciones", "duro", "durisimo"],
    "🫶": ["te apoyo", "contigo siempre", "amor y apoyo", "solidaridad", "familia", "corazon manos"],
    "🤷🏻‍♂️": ["porque", "por que", "duda", "pregunta", "quien"],
    # ── CORPO / SENSI ──
    "👀": ["mira", "mirar", "te miro", "mirando", "te veo", "ojos encima", "todos te miran", "ojos", "observar", "vista", "ojo", "ver", "viendo", "ciego"],
    "👁️": ["vision", "vigilancia", "te veo todo", "ojo que todo lo ve"],
    "👂": ["escucha", "escuchar", "escuchando", "escuchame", "escucho", "oido", "oreja", "oyendo"],
    "🍑": ["culo", "culito", "chapa", "nalgas", "booty", "cadera", "curvas", "bien formada", "cuerpazo"],
    "🍒": ["tetota", "tetotas", "boobies", "boobie", "pecho", "pechos", "seno", "senos", "chichis"],
    "🍆": ["bicho", "eggplant", "verga", "pinga", "miembro"],
    "💪": ["musculo", "fuerza", "gym", "entreno", "entrenando", "fuerte", "pesa", "jangueo gym", "fitness"],
    "🦵": ["pierna", "piernas", "patea", "patada", "correr rapido"],
    "🦶": ["pie", "pies", "caminar", "pasos", "descalzo"],
    "🧠": ["cerebro", "inteligente", "inteligencia", "listo", "lista", "pensamiento", "mente brillante", "estrategia", "calculo"],
    "🪞": ["espejo", "reflejo", "me miro", "narcisismo", "vanidad", "presencia", "narcisista"],
    # ── OGGETTI / SIMBOLI ──
    "💡": ["idea", "se me ocurrio", "iluminacion", "eureka", "ocurrencia", "bombilla"],
    "🎯": ["objetivo", "meta", "acertar", "punteria", "apuntar", "diana", "al blanco", "on target"],
    "🔑": ["llave", "clave", "la clave es", "secreto del exito", "acceso", "contraseña", "codigo", "abrir", "llave maestra"],
    "🗝️": ["secreto guardado", "acceso secreto"],
    "🧲": ["atraer", "atraccion", "imantado", "magnetico"],
    "🔮": ["predecir", "futuro", "adivina", "clarividente", "lo se todo", "bola cristal"],
    "📝": ["papeles", "contrato", "firmar contrato", "deal"],
    "📦": ["paquete", "caja", "envio", "delivery", "llegó", "paquete llego"],
    "⌚️": ["reloj", "tiempo", "hora", "minuto", "segundo", "tarde", "temprano", "espera", "watch"],
    "💍": ["sortija", "compromiso", "matrimonio", "casarse", "propuesta", "te caso"],
    # ── ABBIGLIAMENTO / ACCESSORI ──
    "🏠": ["casa", "hogar", "vivienda", "residencia", "domicilio", "habitación", "habitacion", "cuarto", "piso", "departamento", "home", "penthouse"],
    "👩": ["morena", "rubia", "peli roja", "pelirroja", "chica", "muchacha"],
    "👖": ["pantalon", "pantalones", "mahon", "jean", "jeans", "denim"],
    "🕶": ["gafas", "lentes oscuros", "rayban", "oscuros", "sunglasses", "lentes", "oculares"],
    "👗": ["vestido", "ropa elegante", "outfit", "look", "bien vestida", "arreglada", "traje"],
    "👠": ["tacon", "zapatos altos", "stiletto", "heels", "de tacon", "tacones", "tacos"],
    "👟": ["tenis", "sneakers", "zapatillas", "jordan", "nike", "adidas", "yeezy", "flow calle"],
    "🧢": ["gorra", "gorro", "cap", "snapback", "fitted", "hat"],
    "👙": ["panties", "panti", "panty", "bikini", "playa ropa", "bañador", "traje baño"],
    "🧸": ["muneca", "muñeca", "barbie", "bambola"],
    # ── NATURA / CLIMA ──
    "🌴": ["palmera", "tropical", "caribe", "isla", "vacaciones", "paraiso", "playa tropical", "resort", "cancun", "punta cana", "miami beach", "riviera", "sunny"],
    "🌊": ["playa", "arena", "costa", "orilla", "surf", "olas", "ola", "beach", "seaside", "beachside"],
    "☀️": ["sol", "dia", "amanecer", "mañana", "luz", "verano", "soleado", "sunshine", "rayos de sol"],
    "🌙": ["luna", "noche", "madrugada", "nocturno", "night", "trasnochando", "de noche", "a las 3am", "en la noche", "de madrugada", "moonlight", "oscuro", "eclipse"],
    "✨": ["brillo", "brillar", "shining", "glowing", "glow up", "resplandor", "destello", "radiante", "magia", "aura"],
    "⭐️": ["estrella", "estrellas", "star", "superstar", "pegado", "brilla como estrella", "fugaz", "constelacion"],
    "⚡": ["energia", "potencia", "poderoso", "poderosa", "velocidad extrema", "electricidad", "voltaje", "chispa", "power", "fuerza electrica", "rayo", "electrico", "veloz"],
    "💥": ["explosion", "explota", "bang", "impacto", "bombazo", "boom", "golpe", "rompe pista"],
    "🌧": ["lluvia", "llover", "tormenta", "aguacero", "bajo la lluvia", "trueno"],
    "💧": ["gota", "agua", "sudor"],
    "💦": ["moja'", "mojado", "mojaido"],
    "😋": ["lamber", "mamar", "chupar"],
    "❄️": ["frio", "helado", "congelado", "fresco", "ice cold", "nieve", "nevar", "invierno", "frio extremo"],
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
    "👽": ["alien", "extraterrestre", "marciano", "ovni", "abduccion"],
    # ── SPORT / FITNESS ──
    "🏋️": ["pesas", "levantamiento", "fuerza gym", "entreno pesado"],
    "🥊": ["boxeo", "pelea boxeo", "guantes", "ring", "knockout", "ko", "boxer"],
    "⚽": ["futbol", "soccer", "gol", "pelota", "balon"],
    "🏀": ["basketball", "basquet", "canasta", "aro", "nba"],
    "🎾": ["tenis raqueta", "raqueta", "saque"],
    "🏊": ["nadar", "nadando", "piscina", "natacion"],
    "🏄": ["surfear", "surfer", "tabla surf", "ola surfear"],
    "🤸": ["acrobacia", "flexible", "gimnasia", "salto"],
    "🎿": ["esqui", "nieve esqui", "montana nieve"],
    "🏇": ["caballo", "carrera caballos", "hipodromo", "jinete"],
    # ── ANIMALI ──
    "🦁": ["leon", "leona", "rugido", "fiero", "rey de la selva", "fiera"],
    "🦅": ["aguila", "volar alto", "libertad", "alto vuelo", "aguila real", "cumbre"],
    "🦋": ["mariposa", "transformacion", "nueva vida", "cambio", "evolucionar", "glow up cambio", "vuelo", "alas"],
    "🐝": ["abeja", "miel", "abeja reina", "productiva", "productivo", "trabajadora"],
    "🐈": ["gato", "gatita", "gatito", "felina", "michi", "leona felina", "tigresa"],
    "🐶": ["perro", "perra", "cachorro"],
    "🐯": ["tigre", "tigresa", "feroz", "salvaje", "cazador"],
    "🦊": ["zorro", "astuto", "zorra", "manipulador"],
    "🐺": ["lobo", "manada", "solitario", "feroz salvaje"],
    "🦈": ["tiburon", "peligroso", "acecho", "depredador"],
    "🐉": ["dragon", "fuego dragon", "leyenda bestia", "poder bestia"],
    "🦄": ["unicornio", "magico", "especial", "unico", "extraordinario"],
    "🐸": ["sapo", "rana", "saltando"],
    # ── CIBO ──
    "🍔": ["hamburguesa", "burger", "comida", "hambre"],
    "🌮": ["taco", "tacos", "picante", "mexicana"],
    "🍫": ["chocolate", "dulce", "cacao", "bombon"],
    "🍬": ["caramelo", "chicle", "gomita", "azucar"],
    "☕️": ["cafe", "cafecito", "desayuno", "despertar"],
    "🍕": ["pizza", "queso derretido", "pepperoni", "slice"],
    "🍜": ["ramen", "sopa", "tallarines", "fideos"],
    "🌯": ["burritos", "wrap", "enrollado", "comida latina"],
    "🍗": ["pollo", "pechuga", "muslo", "fried chicken", "frito"],
    "🥩": ["carne", "bistec", "asado", "parrilla", "bbq", "churrasco"],
    "🍣": ["sushi", "japonesa", "rollo", "atun"],
    "🥗": ["ensalada", "saludable", "dieta", "verde comer"],
    "🍓": ["fresa", "dulce fruta", "rico", "delicioso"],
    "🍉": ["sandia", "verano fruta", "refrescante"],
    "🍇": ["uvas", "vino fruta", "racimo"],
    "🥝": ["kiwi", "exotico", "tropical fruta"],
    "🍦": ["helado", "nieve dulce", "cono", "paleta"],
    "🍰": ["rebanada", "dulce fiesta", "postre"],
    # ── BANDIERE / PAESI ──
    "🌍": ["mundo", "tierra", "global", "planeta tierra", "internacional"],
    "🇵🇷": ["puerto_rico", "pr", "boricua", "borinquen", "san juan", "bayamon", "carolina"],
    "🇨🇴": ["colombia", "parcero", "parcera", "medellin", "bogota", "colombiano", "colombiana", "paisa", "cali"],
    "🇲🇽": ["mexico", "mexicano", "mexicana", "cdmx", "monterrey", "guadalajara"],
    "🇦🇷": ["argentina", "argentino", "buenos aires", "che", "pibe"],
    "🇩🇴": ["republica_dominicana", "dominicano", "rd", "dembow", "tigere", "santo domingo"],
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
    "🇵🇹": ["portugal", "portugues", "portuguesa", "lisboa", "porto"],
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
    "🔟": ["diez", "ten", "10"],
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

_COMPILED_PATTERNS = []
for _word in sorted(FLAT_EMOJI_MAP.keys(), key=len, reverse=True):
    _word_clean = _word.replace("_", " ")
    _COMPILED_PATTERNS.append(
        (re.compile(rf'\b{re.escape(_word_clean)}\b'), FLAT_EMOJI_MAP[_word])
    )

_NUMBER_RE = re.compile(r'\b\d+\b')
_DIGIT_MAP = {'0': '0️⃣', '1': '1️⃣', '2': '2️⃣', '3': '3️⃣', '4': '4️⃣',
              '5': '5️⃣', '6': '6️⃣', '7': '7️⃣', '8': '8️⃣', '9': '9️⃣'}
_DIGIT_EMOJIS = set(_DIGIT_MAP.values())
_HTTP_SESSION = requests.Session()

@lru_cache(maxsize=2048)
def _extract_emojis_cached(clean_text):
    found_emojis = []
    seen = set()

    for num_str in _NUMBER_RE.findall(clean_text):
        combo = "".join(_DIGIT_MAP.get(d, '') for d in num_str)
        if combo and combo not in seen:
            found_emojis.append(combo)
            seen.add(combo)

    for pattern, emoji_to_add in _COMPILED_PATTERNS:
        if pattern.search(clean_text):
            if emoji_to_add in _DIGIT_EMOJIS:
                if any(emoji_to_add in ex and ex != emoji_to_add for ex in found_emojis):
                    continue
            if emoji_to_add not in seen:
                found_emojis.append(emoji_to_add)
                seen.add(emoji_to_add)

        if len(found_emojis) >= 3:
            break

    return tuple(found_emojis[:3])


def extract_emojis(text):
    if not text:
        return []
    return list(_extract_emojis_cached(text.lower()))

def get_filename_for_emoji(emoji_char):
    if emoji_char in EMOJI_DICT:
        return EMOJI_DICT[emoji_char][0] + ".png"
    return "default.png"

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
    for emoji_char, codepoint in FLAG_EMOJI_CODEPOINTS.items():
        filename = get_filename_for_emoji(emoji_char)
        path = os.path.join(assets_dir, filename)
        if os.path.exists(path):
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