/// Modelos de datos que devuelve la API de Bioyologic.
library;

double? _d(Object? v) => (v as num?)?.toDouble();

class Analysis {
  Analysis.fromJson(Map<String, dynamic> j)
      : id = j['id'] as int,
        projectId = j['project_id'] as int?,
        projectName = j['project_name'] as String?,
        sampleName = j['sample_name'] as String,
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
        species = j['species'] == null ? null : SpeciesPrediction.fromJson(j['species'] as Map<String, dynamic>);

  final int id;
  final int? projectId;
  final String? projectName;
  final String sampleName;
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
        progress = _d(j['progress'])!;

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
