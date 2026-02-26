# -*- coding: utf-8 -*-
from odoo import models, fields, api  # type: ignore
from odoo.exceptions import ValidationError
import re
import requests
import json
import logging

_logger = logging.getLogger(__name__)

# Mapping région → codes pays
REGION_COUNTRIES = {
    'Europe': [
        'FR', 'DE', 'ES', 'IT', 'PT', 'BE', 'NL', 'LU', 'CH', 'AT',
        'PL', 'CZ', 'SK', 'HU', 'RO', 'BG', 'HR', 'SI', 'RS', 'GR',
        'SE', 'NO', 'DK', 'FI', 'IE', 'GB', 'IS', 'LT', 'LV', 'EE',
        'AL', 'BA', 'ME', 'MK', 'MD', 'UA', 'BY', 'RU', 'TR', 'CY',
        'MT', 'LI', 'MC', 'SM', 'VA', 'AD',
    ],
    'Africa': [
        'MA', 'DZ', 'TN', 'LY', 'EG', 'SD', 'ET', 'NG', 'GH', 'CI',
        'SN', 'CM', 'KE', 'TZ', 'UG', 'RW', 'ZA', 'ZW', 'ZM', 'AO',
        'MZ', 'MG', 'MU', 'CD', 'CG', 'GA', 'BJ', 'TG', 'BF', 'ML',
        'NE', 'TD', 'MR', 'SO', 'DJ', 'ER', 'SS', 'CF', 'GN', 'GW',
        'SL', 'LR', 'GM', 'CV', 'ST', 'GQ', 'BI', 'MW', 'LS', 'SZ',
        'NA', 'BW', 'KM', 'SC',
    ],
    'America': [
        'US', 'CA', 'MX', 'BR', 'AR', 'CL', 'CO', 'PE', 'VE', 'EC',
        'BO', 'PY', 'UY', 'GY', 'SR', 'GT', 'HN', 'SV', 'NI', 'CR',
        'PA', 'CU', 'DO', 'HT', 'JM', 'TT', 'BB', 'LC', 'VC', 'GD',
        'AG', 'DM', 'KN', 'BS', 'BZ',
    ],
    'Asia': [
        'CN', 'JP', 'KR', 'IN', 'PK', 'BD', 'LK', 'NP', 'MM', 'TH',
        'VN', 'KH', 'LA', 'MY', 'SG', 'ID', 'PH', 'TW', 'HK', 'MO',
        'MN', 'KZ', 'UZ', 'TM', 'KG', 'TJ', 'AF', 'AZ', 'GE', 'AM',
    ],
    'Oceania': [
        'AU', 'NZ', 'PG', 'FJ', 'SB', 'VU', 'WS', 'TO', 'KI', 'FM',
        'MH', 'PW', 'NR', 'TV', 'CK', 'NU', 'WF', 'PF', 'NC',
    ],
    'Middle East': [
        'SA', 'AE', 'QA', 'KW', 'BH', 'OM', 'YE', 'IQ', 'IR', 'SY',
        'LB', 'JO', 'PS',
    ],
}



# ================================
# Modèle pour les mots-clés
# ================================
class PisteKeyword(models.Model):
    _name = 'piste.keyword'
    _description = 'Mot-clé'

    name = fields.Char(string="Mot-clé", required=True)


# ================================
# Modèle Région géographique
# ================================
class PisteRegion(models.Model):
    _name = 'piste.region'
    _description = 'Région géographique'

    name = fields.Char(string="Région", required=True)
    country_group_name = fields.Char(string="Nom du groupe Odoo")


# ================================
# Modèle Veille commerciale
# ================================
class PisteSource(models.Model):
    _name = 'piste.source'
    _description = 'Veille commerciale'
    _rec_name = 'name'
    _order = 'name'

    # ===== IDENTIFICATION =====
    name = fields.Char(string="Nom de la veille", required=True)
    description = fields.Text(string="Description / Notes")
    active = fields.Boolean(string="Actif", default=True)

    # ===== MOTS-CLÉS =====
    keywords_required_ids = fields.Many2many(
        'piste.keyword',
        string="Mots-clés obligatoires",
        required=True
    )

    # ===== PLATEFORMES =====
    platform_marches_publics = fields.Boolean(string="Marchés Publics Gouv (Officiel)")
    platform_emarches = fields.Boolean(string="e-marchespublics.com")
    platform_francetenders = fields.Boolean(string="France Tenders")
    platform_appelaprojets = fields.Boolean(string="Appel à Projets")
    platform_marchesonline = fields.Boolean(string="Marchés Online (Payant)")
    platform_tenderimpulse = fields.Boolean(string="Tender Impulse (Payant)")
    platform_globaltenders = fields.Boolean(string="Global Tenders (Payant)")
    platform_deepbloo = fields.Boolean(string="DeepBloo (Payant)")
    platform_batieu = fields.Boolean(string="Bati EU (Payant)")
    platform_boamp = fields.Boolean(string="BOAMP (Bulletin Officiel)")
    platform_ted = fields.Boolean(string="TED - Tenders Electronic Daily (EU)")

    # ===== CRITÈRES COMMERCIAUX =====
    budget_min = fields.Integer(string="Budget minimum (€)")
    budget_max = fields.Integer(string="Budget maximum (€)")

    duration_short = fields.Boolean(string="Court terme (< 3 mois)")
    duration_medium = fields.Boolean(string="Moyen terme (3-6 mois)")
    duration_long = fields.Boolean(string="Long terme (6+ mois)")

    client_pme = fields.Boolean(string="PME / Startups")
    client_large = fields.Boolean(string="Grande entreprise")

    # ===== LOCALISATION =====
    geo_zone_region_ids = fields.Many2many(
        'piste.region',
        string="Régions ciblées"
    )

    geo_zones = fields.Many2many(
        'res.country',
        'piste_source_country_rel',
        'source_id',
        'country_id',
        string="Pays ciblés"
    )

    geo_zone_allowed_country_ids = fields.Many2many(
        'res.country',
        'piste_source_allowed_country_rel',
        'source_id',
        'country_id',
        string="Pays autorisés (filtre)",
        compute='_compute_geo_zone_allowed_country_ids',
        store=True,
    )

    @api.depends('geo_zone_region_ids')
    def _compute_geo_zone_allowed_country_ids(self):
        all_countries = self.env['res.country'].search([])
        for rec in self:
            if not rec.geo_zone_region_ids:
                rec.geo_zone_allowed_country_ids = all_countries
                continue
            region_names = rec.geo_zone_region_ids.mapped('country_group_name')
            region_names = [r for r in region_names if r]
            if not region_names:
                rec.geo_zone_allowed_country_ids = all_countries
                continue
            all_codes = []
            for rname in region_names:
                all_codes += REGION_COUNTRIES.get(rname, [])
            all_codes = list(set(all_codes))
            rec.geo_zone_allowed_country_ids = self.env['res.country'].search([
                ('code', 'in', all_codes)
            ])

    @api.onchange('geo_zone_region_ids')
    def _onchange_geo_zone_region_ids(self):
        self._compute_geo_zone_allowed_country_ids()
        if self.geo_zones and self.geo_zone_allowed_country_ids:
            self.geo_zones = self.geo_zones.filtered(
                lambda c: c in self.geo_zone_allowed_country_ids
            )
        elif not self.geo_zone_allowed_country_ids:
            self.geo_zones = [(5, 0, 0)]

    # ===== PLANIFICATION =====
    automation_type = fields.Selection(
        [('manual', 'Manuel'), ('auto', 'Automatique')],
        string="Type de planification",
        required=True,
        default='manual'
    )

    auto_frequency = fields.Selection([
        ('daily', 'Chaque jour'),
        ('weekly', 'Chaque semaine'),
        ('custom', 'Personnalisée'),
    ], string="Fréquence")

    auto_date_start = fields.Date(string="Date de début")
    auto_date_end = fields.Date(string="Date de fin")

    # Selection avec clés string "HH:MM" — compatible avec l'ancienne colonne varchar en base
    # Affichage identique au widget float_time (ex: 08:00)
    auto_time = fields.Selection([
        ('00:00', '00:00'), ('01:00', '01:00'), ('02:00', '02:00'),
        ('03:00', '03:00'), ('04:00', '04:00'), ('05:00', '05:00'),
        ('06:00', '06:00'), ('07:00', '07:00'), ('08:00', '08:00'),
        ('09:00', '09:00'), ('10:00', '10:00'), ('11:00', '11:00'),
        ('12:00', '12:00'), ('13:00', '13:00'), ('14:00', '14:00'),
        ('15:00', '15:00'), ('16:00', '16:00'), ('17:00', '17:00'),
        ('18:00', '18:00'), ('19:00', '19:00'), ('20:00', '20:00'),
        ('21:00', '21:00'), ('22:00', '22:00'), ('23:00', '23:00'),
    ], string="Heure d'exécution", default='08:00')

    custom_interval = fields.Integer(string="Répéter tous les", default=1)
    custom_interval_unit = fields.Selection([
        ('hours', 'Heure(s)'),
        ('days', 'Jour(s)'),
        ('weeks', 'Semaine(s)'),
        ('months', 'Mois'),
    ], string="Unité", default='days')

    # ===== NOTIFICATIONS =====
    notify_email = fields.Boolean(string="Notification par email", default=False)
    notify_odoo = fields.Boolean(string="Notification Odoo", default=True)

    notify_emails = fields.Text(
        string="Emails des destinataires",
        help="Saisissez une ou plusieurs adresses email, séparées par une virgule, "
             "un point-virgule ou un retour à la ligne.\nEx : alice@example.com, bob@example.com"
    )


    # ===== RELATION AVEC LES OFFRES =====
    offer_ids = fields.One2many('piste.offer', 'source_id', string='Offres trouvées')
    offer_count = fields.Integer(string="Nombre d'offres", compute='_compute_offer_count', store=True)
    last_search_date = fields.Datetime(string="Dernière recherche")

    # ===== MÉTHODES =====

    def name_get(self):
        result = []
        for rec in self:
            result.append((rec.id, f"Veille commerciale – {rec.name}"))
        return result

    @api.depends('offer_ids')
    def _compute_offer_count(self):
        for source in self:
            source.offer_count = len(source.offer_ids)

    def action_view_offers(self):
        return {
            'type': 'ir.actions.act_window',
            'name': f'Offres - {self.name}',
            'res_model': 'piste.offer',
            'view_mode': 'tree,form',
            'domain': [('source_id', '=', self.id)],
            'context': {'default_source_id': self.id}
        }

    # ===== SCRAPING N8N =====

    def action_run_scrape(self):
        self.ensure_one()

        n8n_webhook_url = "http://localhost:5678/webhook-test/piste-run"

        payload = {
            'id': self.id,
            'name': self.name,
            'keywords_required': [kw.name for kw in self.keywords_required_ids],
            'platforms': {
                'marches_publics': self.platform_marches_publics,
                'emarches': self.platform_emarches,
                'boamp': self.platform_boamp,
                'francetenders': self.platform_francetenders,
                'marchesonline': self.platform_marchesonline,
                'globaltenders': self.platform_globaltenders,
                'batieu': self.platform_batieu,
                'ted': self.platform_ted,
                'appelaprojets': self.platform_appelaprojets,
                'tenderimpulse': self.platform_tenderimpulse,
                'deepbloo': self.platform_deepbloo,
            },
            'budget_min': self.budget_min,
            'budget_max': self.budget_max,
            'geo_zones': [c.code for c in self.geo_zones],
            'geo_regions': [r.name for r in self.geo_zone_region_ids],
            'frequency': self.auto_frequency or '',
            'auto_date_start': str(self.auto_date_start) if self.auto_date_start else '',
            'auto_date_end': str(self.auto_date_end) if self.auto_date_end else '',
            'auto_time': self.auto_time or '',
            'custom_interval': self.custom_interval or 1,
            'custom_interval_unit': self.custom_interval_unit or '',
            'automation_type': self.automation_type,
            'notify_email': self.notify_email,
            'notify_odoo': self.notify_odoo,
            'notify_emails': self._parse_emails(self.notify_emails),
            'duration_short': self.duration_short,
            'duration_medium': self.duration_medium,
            'duration_long': self.duration_long,
            'client_pme': self.client_pme,
            'client_large': self.client_large,
            'description': self.description or '',
            'creator_id': self.creator_id.id if self.creator_id else None,
        }

        try:
            response = requests.post(
                n8n_webhook_url,
                headers={'Content-Type': 'application/json'},
                data=json.dumps(payload),
                timeout=10
            )
            _logger.info("Scrape envoyé : %s -> %s", self.name, response.status_code)
        except Exception as e:
            _logger.error("Erreur n8n : %s", str(e))