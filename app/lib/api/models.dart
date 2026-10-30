/// Modelos de datos que devuelve la API de Bioyologic.
library;

double? _d(Object? v) => (v as num?)?.toDouble();

class Analysis {
  Analysis.fromJson(Map<String, dynamic> j)
      : id = j['id'] as int,
        projectId = j['project_id'] as int?,
        projectName = j['project_name'] as String?,
        sampleName = j['sample_name'] as String,
        sampleGroup = (j['sample_group'] as String?) ?? '',
        quality = j['quality'] == null ? null : PhotoQuality.fromJson(j['quality'] as Map<String, dynamic>),
        createdAt = DateTime.parse(j['created_at'] as String).toLocal(),
        dilution = _d(j['dilution']),
        volumeMl = _d(j['volume_ml']),
        mmPerPx = _d(j['mm_per_px']),
        notes = (j['notes'] as String?) ?? '',
        summary = Summary.fromJson(j['summary'] as Map<String, dynamic>),
        colonies = (j['colonies'] as List?)
            ?.map((c) => Colony.fromJson(c as Map<String, dynamic>))
            .toList(),
        removedColonies = ((j['removed_colonies'] as List?) ?? [])
            .map((c) => Colony.fromJson(c as Map<String, dynamic>))
            .toList(),
        imageSize = (j['image_size'] as List?)?.map((v) => (v as num).toDouble()).toList(),
        correction = j['correction'] == null ? null : Correction.fromJson(j['correction'] as Map<String, dynamic>),
        imageUrls = Map<String, String>.from(j['image_urls'] as Map),
        reportUrl = j['report_url'] as String,
        species = j['species'] == null ? null : SpeciesPrediction.fromJson(j['species'] as Map<String, dynamic>),
        authorName = (j['author_name'] as String?) ?? '',
        isMine = (j['is_mine'] as bool?) ?? true,
        canEdit = (j['can_edit'] as bool?) ?? true,
        canCorrect = (j['can_correct'] as bool?) ?? true,
        canReview = (j['can_review'] as bool?) ?? false,
        review = j['review'] == null ? null : Review.fromJson(j['review'] as Map<String, dynamic>),
        incubation = j['incubation'] == null ? null : IncubationRecord.fromJson(j['incubation'] as Map<String, dynamic>);

  /// Quién hizo el análisis (en proyectos compartidos puede ser otro miembro).
  final String authorName;
  final bool isMine;

  /// Renombrar, mover, asignar a muestra y borrar: solo el autor.
  final bool canEdit;

  /// Corregir el conteo: el autor, y en un proyecto compartido también el dueño y los revisores.
  final bool canCorrect;

  /// Aprobar o devolver: dueño o revisor del proyecto compartido, nunca el autor.
  final bool canReview;

  /// Revisión (solo en proyectos compartidos); null si el proyecto no es compartido.
  final Review? review;

  /// Siembra de la que salió la placa, con las horas reales de incubación.
  final IncubationRecord? incubation;

  final int id;
  final int? projectId;
  final String? projectName;
  final String sampleName;

  /// Muestra a la que pertenece la placa (diluciones y réplicas de una misma muestra); '' si ninguna.
  final String sampleGroup;

  /// Control de calidad de la foto (null en análisis anteriores a esta función).
  final PhotoQuality? quality;
  final DateTime createdAt;
  final double? dilution;
  final double? volumeMl;
  final double? mmPerPx;
  final String notes;
  final Summary summary;

  /// Solo viene en el detalle (GET /analyses/{id}), no en los listados.
  final List<Colony>? colonies;

  /// Detecciones del modelo que el usuario quitó a mano (solo en el detalle).
  final List<Colony> removedColonies;

  /// Ancho y alto de la foto original en píxeles.
  final List<double>? imageSize;

  /// Corrección manual del conteo, si la hubo.
  final Correction? correction;
  final Map<String, String> imageUrls;
  final String reportUrl;

  /// Especie de la placa según el clasificador (null si no hay clasificador instalado).
  final SpeciesPrediction? species;

  String get thumbUrl => imageUrls['thumb']!;
  String get annotatedUrl => imageUrls['annotated']!;
  String get originalUrl => imageUrls['original']!;
}

class Stat {
  Stat.fromJson(Map<String, dynamic> j)
      : mean = _d(j['mean'])!,
        std = _d(j['std'])!,
        median = _d(j['median'])!,
        min = _d(j['min'])!,
        max = _d(j['max'])!;

  final double mean, std, median, min, max;
}

class Summary {
  Summary.fromJson(Map<String, dynamic> j)
      : total = j['total'] as int,
        byClass = Map<String, int>.from(j['by_class'] as Map),
        status = j['status'] as String,
        cfuPerMl = _d(j['cfu_per_ml']),
        predominant = Map<String, String?>.from((j['predominant'] as Map?) ?? {}),
        _stats = j['stats'] as Map<String, dynamic>;

  final int total;
  final Map<String, int> byClass;
  final String status;
  final double? cfuPerMl;
  final Map<String, String?> predominant;
  final Map<String, dynamic> _stats;

  Stat? stat(String key) {
    final s = _stats[key];
    return s is Map<String, dynamic> && s.containsKey('mean') ? Stat.fromJson(s) : null;
  }

  Map<String, int> counts(String key) => Map<String, int>.from((_stats[key] as Map?) ?? {});

  /// Diámetro medio en mm si se conoce la escala; si no, en píxeles.
  ({Stat? stat, String unit}) get diameter {
    final mm = stat('diameter_mm');
    return mm != null ? (stat: mm, unit: 'mm') : (stat: stat('diameter_px'), unit: 'px');
  }
}

class Colony {
  Colony.fromJson(Map<String, dynamic> j)
      : id = j['id'] as int,
        className = j['class_name'] as String,
        confidence = _d(j['confidence']),
        speciesConfidence = _d(j['species_confidence']),
        manual = (j['manual'] as bool?) ?? false,
        center = ((j['center'] as List?) ?? [0, 0]).map((v) => (v as num).toDouble()).toList(),
        bbox = ((j['bbox'] as List?) ?? [0, 0, 0, 0]).map((v) => (v as num).toDouble()).toList(),
        m = j['morphology'] as Map<String, dynamic>;

  final int id;
  final String className;

  /// Confianza del detector; null en las colonias agregadas a mano.
  final double? confidence;

  /// Agregada a mano por el usuario (no la detectó el modelo).
  final bool manual;

  /// Centro (x, y) y caja (x1, y1, x2, y2) en píxeles de la foto original.
  final List<double> center;
  final List<double> bbox;
  double get radius => ((bbox[2] - bbox[0]) + (bbox[3] - bbox[1])) / 4;
  final double? speciesConfidence;
  final Map<String, dynamic> m;

  double? get diameterMm => _d(m['diameter_mm']);
  double get diameterPx => _d(m['diameter_px'])!;
  double? num_(String k) => _d(m[k]);
  String get form => m['form'] as String;
  String get margin => m['margin'] as String;
  String get colorHex => m['color_hex'] as String;
  String get colorName => m['color_name'] as String;
  bool get segmented => m['segmented'] as bool;
}

class Project {
  Project.fromJson(Map<String, dynamic> j)
      : id = j['id'] as int,
        name = j['name'] as String,
        description = (j['description'] as String?) ?? '',
        targetSamples = j['target_samples'] as int,
        analysesCount = j['analyses_count'] as int,
        coloniesTotal = j['colonies_total'] as int,
        createdAt = DateTime.parse(j['created_at'] as String).toLocal(),
        lastAnalysisAt = j['last_analysis_at'] == null
            ? null
            : DateTime.parse(j['last_analysis_at'] as String).toLocal(),
        coverUrl = j['cover_url'] as String?,
        progress = _d(j['progress'])!,
        myRole = (j['my_role'] as String?) ?? 'owner',
        shared = (j['shared'] as bool?) ?? false,
        membersCount = (j['members_count'] as int?) ?? 0,
        ownerName = (j['owner_name'] as String?) ?? '',
        unreviewedCount = (j['unreviewed_count'] as int?) ?? 0;

  /// owner | analista | revisor
  final String myRole;
  bool get isOwner => myRole == 'owner';
  bool get canReview => shared && (myRole == 'owner' || myRole == 'revisor');

  /// Tiene otros miembros además del dueño.
  final bool shared;
  final int membersCount;
  final String ownerName;

  /// Análisis del proyecto sin revisar (solo en proyectos compartidos).
  final int unreviewedCount;

  final int id;
  final String name;
  final String description;
  final int targetSamples;
  final int analysesCount;
  final int coloniesTotal;
  final DateTime createdAt;
  final DateTime? lastAnalysisAt;
  final String? coverUrl;
  final double progress;
}

class LibraryEntry {
  LibraryEntry.fromJson(Map<String, dynamic> j)
      : id = j['id'] as String,
        category = j['category'] as String,
        title = j['title'] as String,
        subtitle = j['subtitle'] as String,
        tags = List<String>.from(j['tags'] as List),
        imageUrl = j['image_url'] as String,
        sections = (j['sections'] as List?)
            ?.map((s) => (title: (s as List)[0] as String, body: s[1] as String))
            .toList();

  final String id;
  final String category;
  final String title;
  final String subtitle;
  final List<String> tags;
  final String imageUrl;
  final List<({String title, String body})>? sections;
}

class Stats {
  Stats.fromJson(Map<String, dynamic> j)
      : analyses = j['analyses'] as int,
        colonies = j['colonies'] as int,
        projects = j['projects'] as int;

  final int analyses;
  final int colonies;
  final int projects;
}

class SpeciesCandidate {
  SpeciesCandidate.fromJson(Map<String, dynamic> j)
      : name = j['name'] as String,
        prob = _d(j['prob'])!,
        gram = j['gram'] as String?,
        agar = j['agar'] as String?;

  final String name;
  final double prob;
  final String? gram;
  final String? agar;
}

class SpeciesPrediction {
  SpeciesPrediction.fromJson(Map<String, dynamic> j)
      : identified = j['identified'] as bool,
        top = (j['top'] as List).map((e) => SpeciesCandidate.fromJson(e as Map<String, dynamic>)).toList();

  final bool identified;
  final List<SpeciesCandidate> top;
}

/// Cuenta del usuario en el servidor.
class UserProfile {
  UserProfile.fromJson(Map<String, dynamic> j)
      : id = j['id'] as int,
        email = j['email'] as String,
        name = j['name'] as String,
        role = (j['role'] as String?) ?? '',
        institution = (j['institution'] as String?) ?? '',
        emailVerified = (j['email_verified'] as bool?) ?? true,
        verificationRequired = (j['verification_required'] as bool?) ?? false;

  final int id;
  final String email;
  final String name;
  final String role;
  final String institution;
  final bool emailVerified;

  /// El servidor exige verificar el correo (tiene configurado el envío de correos).
  final bool verificationRequired;

  bool get needsVerification => verificationRequired && !emailVerified;
}

/// Corrección manual del conteo (queda registrada para la trazabilidad).
class Correction {
  Correction.fromJson(Map<String, dynamic> j)
      : at = DateTime.parse(j['at'] as String).toLocal(),
        by = (j['by'] as String?) ?? '',
        detectedTotal = j['detected_total'] as int,
        removed = List<int>.from(j['removed'] as List),
        added = (j['added'] as List)
            .map((a) => (x: _d((a as Map)['x'])!, y: _d(a['y'])!, r: _d(a['r'])!))
            .toList();

  final DateTime at;
  final String by;
  final int detectedTotal;
  final List<int> removed;
  final List<({double x, double y, double r})> added;
}

/// Advertencias sobre la foto: borrosa, oscura, reflejos, placa descentrada o lejana.
class PhotoQuality {
  PhotoQuality.fromJson(Map<String, dynamic> j)
      : ok = (j['ok'] as bool?) ?? true,
        issues = ((j['issues'] as List?) ?? [])
            .map((i) => (code: (i as Map)['code'] as String, message: i['message'] as String))
            .toList();

  final bool ok;
  final List<({String code, String message})> issues;
}

/// Revisión de un análisis en un proyecto compartido.
class Review {
  Review.fromJson(Map<String, dynamic> j)
      : status = j['status'] as String,
        by = (j['by'] as String?) ?? '',
        at = j['at'] == null ? null : DateTime.parse(j['at'] as String).toLocal(),
        note = (j['note'] as String?) ?? '';

  /// pendiente | aprobado | devuelto
  final String status;
  final String by;
  final DateTime? at;
  final String note;

  bool get pending => status == 'pendiente';
}

/// Miembro de un proyecto compartido.
class Member {
  Member.fromJson(Map<String, dynamic> j)
      : userId = j['user_id'] as int,
        name = j['name'] as String,
        role = j['role'] as String,
        email = j['email'] as String?;

  final int userId;
  final String name;

  /// owner | analista | revisor
  final String role;

  /// Solo lo ve el dueño del proyecto (y cada uno el suyo).
  final String? email;
}

String roleLabel(String role) =>
    {'owner': 'Dueño', 'analista': 'Analista', 'revisor': 'Revisor'}[role] ?? role;

/// Siembra en incubación: la app avisa cuando las placas están listas para leer.
class Incubation {
  Incubation.fromJson(Map<String, dynamic> j)
      : id = j['id'] as int,
        name = j['name'] as String,
        projectId = j['project_id'] as int?,
        projectName = j['project_name'] as String?,
        sampleGroup = (j['sample_group'] as String?) ?? '',
        plates = j['plates'] as int?,
        seededAt = DateTime.parse(j['seeded_at'] as String).toLocal(),
        hours = _d(j['hours'])!,
        temperatureC = _d(j['temperature_c']),
        readyAt = DateTime.parse(j['ready_at'] as String).toLocal(),
        notes = (j['notes'] as String?) ?? '',
        doneAt = j['done_at'] == null ? null : DateTime.parse(j['done_at'] as String).toLocal(),
        analysesCount = (j['analyses_count'] as int?) ?? 0,
        createdBy = (j['created_by'] as String?) ?? '',
        isMine = (j['is_mine'] as bool?) ?? true;

  final int id;
  final String name;
  final int? projectId;
  final String? projectName;
  final String sampleGroup;
  final int? plates;
  final DateTime seededAt;
  final double hours;
  final double? temperatureC;
  final DateTime readyAt;
  final String notes;
  final DateTime? doneAt;
  final int analysesCount;
  final String createdBy;
  final bool isMine;

  bool isReady([DateTime? now]) => !(now ?? DateTime.now()).isBefore(readyAt);
}

/// Lo que guarda un análisis de su siembra.
class IncubationRecord {
  IncubationRecord.fromJson(Map<String, dynamic> j)
      : name = j['name'] as String,
        hours = _d(j['hours'])!,
        temperatureC = _d(j['temperature_c']),
        readAfterHours = _d(j['read_after_hours'])!;

  final String name;
  final double hours;
  final double? temperatureC;

  /// Horas reales desde la siembra hasta la foto.
  final double readAfterHours;
}

/// Placa dentro de una muestra.
class SamplePlate {
  SamplePlate.fromJson(Map<String, dynamic> j)
      : id = j['id'] as int,
        sampleName = j['sample_name'] as String,
        createdAt = DateTime.parse(j['created_at'] as String).toLocal(),
        dilution = _d(j['dilution']),
        volumeMl = _d(j['volume_ml']),
        total = j['total'] as int,
        status = j['status'] as String,
        cfuPerMl = _d(j['cfu_per_ml']),
        used = j['used'] as bool,
        thumbUrl = j['thumb_url'] as String;

  final int id;
  final String sampleName;
  final DateTime createdAt;
  final double? dilution;
  final double? volumeMl;
  final int total;
  final String status;
  final double? cfuPerMl;

  /// Entra en el cálculo combinado (placa contable de las diluciones elegidas).
  final bool used;
  final String thumbUrl;
}

/// Muestra con varias placas y su UFC/mL combinada según ISO 4833-1.
class Sample {
  Sample.fromJson(Map<String, dynamic> j)
      : name = j['name'] as String,
        projectId = j['project_id'] as int?,
        projectName = j['project_name'] as String?,
        lastAt = DateTime.parse(j['last_at'] as String).toLocal(),
        cfuPerMl = _d((j['result'] as Map)['cfu_per_ml']),
        estimated = (j['result'] as Map)['estimated'] as bool,
        rule = (j['result'] as Map)['rule'] as String,
        warnings = List<String>.from((j['result'] as Map)['warnings'] as List),
        plates = (j['plates'] as List).map((p) => SamplePlate.fromJson(p as Map<String, dynamic>)).toList();

  final String name;
  final int? projectId;
  final String? projectName;
  final DateTime lastAt;
  final double? cfuPerMl;
  final bool estimated;
  final String rule;
  final List<String> warnings;
  final List<SamplePlate> plates;

  int get usedCount => plates.where((p) => p.used).length;
}
