# -*- coding: utf-8 -*-
# =============================================================================
# Module : crm_menu_override
# Fichier : models/piste_source.py
# Description : Modèle principal de la veille commerciale.
#               Gère la configuration des recherches automatisées,
#               la planification via ir.cron, et l'envoi vers N8N.
# =============================================================================

from odoo import models, fields, api  # type: ignore
from odoo.exceptions import ValidationError
import re
import requests
import json
import logging
from datetime import datetime, date, timedelta

_logger = logging.getLogger(__name__)

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

EMAIL_REGEX = re.compile(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$')


class PisteKeyword(models.Model):
    _name = 'piste.keyword'
    _description = 'Mot-clé'

    name = fields.Char(string="Mot-clé", required=True)


class PisteRegion(models.Model):
    _name = 'piste.region'
    _description = 'Région géographique'

    name = fields.Char(string="Région", required=True)
    country_group_name = fields.Char(string="Nom du groupe Odoo")


class PisteEmail(models.Model):
    _name = 'piste.email'
    _description = 'Adresse email de notification'
    _rec_name = 'email'

    email = fields.Char(string="Email", required=True)

    @api.constrains('email')
    def _check_email(self):
        for rec in self:
            if not EMAIL_REGEX.match(rec.email):
                raise ValidationError(
                    f"L'adresse '{rec.email}' est invalide.\n"
                    "Format attendu : nom@domaine.extension"
                )

    def name_get(self):
        return [(rec.id, rec.email) for rec in self]


class PisteSource(models.Model):
    _name = 'piste.source'
    _description = 'Veille commerciale'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'name'
    _order = 'name'

    # =========================================================================
    # IDENTIFICATION
    # =========================================================================
    name = fields.Char(string="Nom de la veille", required=True)
    description = fields.Text(string="Description / Notes")
    active = fields.Boolean(string="Actif", default=True)

    # =========================================================================
    # MOTS-CLÉS
    # =========================================================================
    keywords_required_ids = fields.Many2many(
        'piste.keyword',
        string="Mots-clés obligatoires"
    )

    @api.constrains('keywords_required_ids')
    def _check_keywords(self):
        for rec in self:
            if not rec.keywords_required_ids:
                raise ValidationError(
                    "Veuillez renseigner au moins un mot-clé obligatoire."
                )

    # =========================================================================
    # PLATEFORMES DE SCRAPING
    # =========================================================================
    platform_achatpublic     = fields.Boolean(string="Achatpublic")
    platform_francemarches   = fields.Boolean(string="France Marchés")
    platform_awsolutions     = fields.Boolean(string="AW Solutions")
    platform_doubletrade     = fields.Boolean(string="DoubleTrade")
    platform_marchespublics  = fields.Boolean(string="MarchesPublics")
    platform_marchessecurise = fields.Boolean(string="Marchés Sécurisés")
    platform_boamp           = fields.Boolean(string="BOAMP")

    # =========================================================================
    # CRITÈRES COMMERCIAUX
    # =========================================================================
    budget_min = fields.Integer(string="Budget minimum (€)")
    budget_max = fields.Integer(string="Budget maximum (€)")
    duration_short = fields.Boolean(string="Court terme (< 3 mois)")
    duration_medium = fields.Boolean(string="Moyen terme (3-6 mois)")
    duration_long = fields.Boolean(string="Long terme (6+ mois)")
    client_pme = fields.Boolean(string="PME / Startups")
    client_large = fields.Boolean(string="Grande entreprise")

    # =========================================================================
    # LOCALISATION
    # =========================================================================
    geo_zone_region_ids = fields.Many2many('piste.region', string="Régions ciblées")

    geo_zones = fields.Many2many(
        'res.country',
        'piste_source_country_rel',
        'source_id', 'country_id',
        string="Pays ciblés"
    )

    geo_zone_allowed_country_ids = fields.Many2many(
        'res.country',
        'piste_source_allowed_country_rel',
        'source_id', 'country_id',
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

    # =========================================================================
    # PLANIFICATION
    # =========================================================================
    automation_type = fields.Selection(
        [('manual', 'Manuel'), ('auto', 'Automatique')],
        string="Type de planification", required=True, default='manual'
    )
    auto_frequency = fields.Selection([
        ('daily', 'Chaque jour'),
        ('weekly', 'Chaque semaine'),
        ('custom', 'Personnalisée'),
    ], string="Fréquence")
    auto_date_start = fields.Date(string="Date de début")
    auto_date_end = fields.Date(string="Date de fin")
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
        ('hours', 'Heure(s)'), ('days', 'Jour(s)'),
        ('weeks', 'Semaine(s)'), ('months', 'Mois'),
    ], string="Unité", default='days')

    # =========================================================================
    # NOTIFICATIONS
    # =========================================================================
    notify_odoo = fields.Boolean(string="Notification Odoo", default=True)
    notify_email = fields.Boolean(string="Notification par email", default=False)
    notify_email_ids = fields.Many2many('piste.email', string="Emails des destinataires")

    # =========================================================================
    # COMPTEURS SMART BUTTONS
    # =========================================================================
    offer_ids = fields.One2many('piste.offer', 'source_id', string='Offres trouvées')
    offer_count = fields.Integer(
        string="Nombre d'offres",
        compute='_compute_offer_count',
        store=True
    )

    crm_lead_count = fields.Integer(
        string="Pistes trouvées",
        compute='_compute_crm_lead_count',
        store=False,
    )

    last_search_date = fields.Datetime(string="Dernière recherche")

    # =========================================================================
    # VALIDATION
    # =========================================================================
    @api.constrains('notify_email_ids', 'notify_email')
    def _check_notify_emails(self):
        for rec in self:
            if rec.notify_email and not rec.notify_email_ids:
                raise ValidationError(
                    "Vous avez activé la notification par email "
                    "mais aucune adresse n'est renseignée."
                )

    # =========================================================================
    # MÉTHODES STANDARD
    # =========================================================================
    def name_get(self):
        return [(rec.id, f"Veille commerciale – {rec.name}") for rec in self]

    @api.depends('offer_ids')
    def _compute_offer_count(self):
        for source in self:
            source.offer_count = len(source.offer_ids)

    def _compute_crm_lead_count(self):
        lead_data = self.env['crm.lead'].read_group(
            domain=[('piste_source_id', 'in', self.ids)],
            fields=['piste_source_id'],
            groupby=['piste_source_id'],
        )
        counts = {d['piste_source_id'][0]: d['piste_source_id_count'] for d in lead_data}
        for source in self:
            source.crm_lead_count = counts.get(source.id, 0)

    # =========================================================================
    # ACTIONS SMART BUTTONS
    # =========================================================================
    def action_view_offers(self):
        return {
            'type': 'ir.actions.act_window',
            'name': f'Offres – {self.name}',
            'res_model': 'piste.offer',
            'view_mode': 'tree,form',
            'domain': [('source_id', '=', self.id)],
            'context': {'default_source_id': self.id},
        }

    def action_view_crm_leads(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Pistes trouvées – {self.name}',
            'res_model': 'crm.lead',
            'view_mode': 'tree,form,kanban',
            'domain': [('piste_source_id', '=', self.id)],
            'context': {
                'default_piste_source_id': self.id,
                'default_type': 'lead',
            },
        }

    def action_view_crm_opportunities(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Opportunités – {self.name}',
            'res_model': 'crm.lead',
            'view_mode': 'tree,form,kanban',
            'domain': [
                ('piste_source_id', '=', self.id),
                ('type', '=', 'opportunity'),
            ],
            'context': {
                'default_piste_source_id': self.id,
                'default_type': 'opportunity',
            },
        }

    # =========================================================================
    # GESTION CRON AUTOMATIQUE
    # =========================================================================
    def _cron_name(self):
        return f'Veille N8N – {self.name} [{self.id}]'

    def _get_cron_interval(self):
        if self.auto_frequency == 'daily':
            return 1, 'days'
        elif self.auto_frequency == 'weekly':
            return 7, 'days'
        elif self.auto_frequency == 'custom':
            unit_map = {
                'hours': 'hours', 'days': 'days',
                'weeks': 'days', 'months': 'months',
            }
            interval = self.custom_interval or 1
            unit = self.custom_interval_unit or 'days'
            if unit == 'weeks':
                interval = interval * 7
            return interval, unit_map.get(unit, 'days')
        return 1, 'days'

    def _create_or_update_cron(self):
        self.ensure_one()
        if self.automation_type != 'auto':
            self._delete_cron()
            return

        hour = int((self.auto_time or '08:00').split(':')[0])
        nextcall = datetime.combine(
            self.auto_date_start or date.today(),
            datetime.min.time()
        ).replace(hour=hour, minute=0, second=0)

        now = datetime.now()
        if nextcall < now:
            nextcall = now.replace(hour=hour, minute=0, second=0, microsecond=0)
            if nextcall < now:
                nextcall += timedelta(days=1)

        interval_number, interval_type = self._get_cron_interval()

        cron_vals = {
            'name': self._cron_name(),
            'model_id': self.env['ir.model']._get('piste.source').id,
            'state': 'code',
            'code': f'model.browse({self.id}).action_run_scrape()',
            'interval_number': interval_number,
            'interval_type': interval_type,
            'nextcall': nextcall,
            'numbercall': -1,
            'active': True,
            'user_id': self.env.ref('base.user_root').id,
        }

        existing = self.env['ir.cron'].sudo().search(
            [('name', '=', self._cron_name())], limit=1
        )
        if existing:
            existing.sudo().write(cron_vals)
        else:
            self.env['ir.cron'].sudo().create(cron_vals)

    def _delete_cron(self):
        cron = self.env['ir.cron'].sudo().search(
            [('name', '=', self._cron_name())], limit=1
        )
        if cron:
            cron.sudo().unlink()

    # =========================================================================
    # OVERRIDE CREATE / WRITE / UNLINK
    # =========================================================================
    @api.model

    def default_get(self, fields_list):
        """
        Valeurs par défaut à la création d'une nouvelle veille :
        - Région : Europe
        - Pays : France
        """
        res = super().default_get(fields_list)

        # Région Europe par défaut
        europe = self.env['piste.region'].search([('name', '=', 'Europe')], limit=1)
        if europe:
            res['geo_zone_region_ids'] = [(6, 0, [europe.id])]

        # Pays France par défaut
        france = self.env['res.country'].search([('code', '=', 'FR')], limit=1)
        if france:
            res['geo_zones'] = [(6, 0, [france.id])]

        return res


    def create(self, vals):
        record = super().create(vals)
        record._create_or_update_cron()
        return record

    def write(self, vals):
        res = super().write(vals)
        planning_fields = {
            'automation_type', 'auto_frequency', 'auto_date_start',
            'auto_date_end', 'auto_time', 'custom_interval',
            'custom_interval_unit', 'name'
        }
        if planning_fields.intersection(vals.keys()):
            for rec in self:
                rec._create_or_update_cron()
        return res

    def unlink(self):
        for rec in self:
            rec._delete_cron()
        return super().unlink()

    # =========================================================================
    # SCRAPING N8N
    # =========================================================================
    def action_run_scrape(self):
        self.ensure_one()

        if self.automation_type == 'auto' and self.auto_date_end:
            if date.today() > self.auto_date_end:
                self._delete_cron()
                return

        n8n_webhook_url = "http://localhost:5678/webhook/piste-run"

        payload = {
            'id': self.id,
            'name': self.name,
            'keywords_required': [kw.name for kw in self.keywords_required_ids],
            'platforms': {
                'achatpublic':      self.platform_achatpublic,
                'francemarches':    self.platform_francemarches,
                'awsolutions':      self.platform_awsolutions,
                'doubletrade':      self.platform_doubletrade,
                'marchespublics':   self.platform_marchespublics,
                'marchessecurise':  self.platform_marchessecurise,
                'boamp':            self.platform_boamp,
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
            'notify_odoo': self.notify_odoo,
            'notify_email': self.notify_email,
            'notify_emails': [e.email for e in self.notify_email_ids],
            'duration_short': self.duration_short,
            'duration_medium': self.duration_medium,
            'duration_long': self.duration_long,
            'client_pme': self.client_pme,
            'client_large': self.client_large,
            'description': self.description or '',
            'creator_id': self.create_uid.id if self.create_uid else None,
        }

        try:
            response = requests.post(
                n8n_webhook_url,
                headers={'Content-Type': 'application/json'},
                data=json.dumps(payload),
                timeout=10
            )
            self.sudo().write({'last_search_date': datetime.now()})
            _logger.info("Scrape envoyé : %s → HTTP %s", self.name, response.status_code)

            if self.notify_odoo:
                self.message_post(
                    body=(
                        f"✅ Veille <b>{self.name}</b> lancée avec succès le "
                        f"{datetime.now().strftime('%d/%m/%Y à %H:%M')}.<br/>"
                        f"Mots-clés : {', '.join([kw.name for kw in self.keywords_required_ids])}"
                    ),
                    message_type='notification',
                    subtype_xmlid='mail.mt_note',
                )

            if self.notify_email and self.notify_email_ids:
                emails = ','.join(self.notify_email_ids.mapped('email'))
                keywords_str = ', '.join([kw.name for kw in self.keywords_required_ids])
                self.env['mail.mail'].sudo().create({
                    'subject': f'[Veille] {self.name} – recherche lancée',
                    'body_html': f'''
                        <p>Bonjour,</p>
                        <p>La veille commerciale <b>{self.name}</b> vient d'être lancée.</p>
                        <p><b>Date :</b> {datetime.now().strftime('%d/%m/%Y à %H:%M')}</p>
                        <p><b>Mots-clés :</b> {keywords_str}</p>
                        <br/>
                        <p>— Odoo CRM</p>
                    ''',
                    'email_to': emails,
                }).send()
                _logger.info("Email de notification envoyé à : %s", emails)

        except Exception as e:
            _logger.error("Erreur envoi webhook N8N pour '%s' : %s", self.name, str(e))