# -*- coding: utf-8 -*-
# =============================================================================
# Module : crm_menu_override
# Fichier : models/piste_source.py
# Description : Veille commerciale avec 5 critères IA - poids manuels (total = 100%)
# =============================================================================

from odoo import models, fields, api
from odoo.exceptions import ValidationError
import re
import requests
import json
import logging
from datetime import datetime, date, timedelta

_logger = logging.getLogger(__name__)

REGION_COUNTRIES = {
    'Europe': ['FR', 'DE', 'ES', 'IT', 'PT', 'BE', 'NL', 'LU', 'CH', 'AT', 'PL', 'CZ', 'SK', 'HU', 'RO', 'BG', 'HR', 'SI', 'RS', 'GR', 'SE', 'NO', 'DK', 'FI', 'IE', 'GB', 'IS', 'LT', 'LV', 'EE', 'AL', 'BA', 'ME', 'MK', 'MD', 'UA', 'BY', 'RU', 'TR', 'CY', 'MT', 'LI', 'MC', 'SM', 'VA', 'AD'],
    'Africa': ['MA', 'DZ', 'TN', 'LY', 'EG', 'SD', 'ET', 'NG', 'GH', 'CI', 'SN', 'CM', 'KE', 'TZ', 'UG', 'RW', 'ZA', 'ZW', 'ZM', 'AO', 'MZ', 'MG', 'MU', 'CD', 'CG', 'GA', 'BJ', 'TG', 'BF', 'ML', 'NE', 'TD', 'MR', 'SO', 'DJ', 'ER', 'SS', 'CF', 'GN', 'GW', 'SL', 'LR', 'GM', 'CV', 'ST', 'GQ', 'BI', 'MW', 'LS', 'SZ', 'NA', 'BW', 'KM', 'SC'],
    'America': ['US', 'CA', 'MX', 'BR', 'AR', 'CL', 'CO', 'PE', 'VE', 'EC', 'BO', 'PY', 'UY', 'GY', 'SR', 'GT', 'HN', 'SV', 'NI', 'CR', 'PA', 'CU', 'DO', 'HT', 'JM', 'TT', 'BB', 'LC', 'VC', 'GD', 'AG', 'DM', 'KN', 'BS', 'BZ'],
    'Asia': ['CN', 'JP', 'KR', 'IN', 'PK', 'BD', 'LK', 'NP', 'MM', 'TH', 'VN', 'KH', 'LA', 'MY', 'SG', 'ID', 'PH', 'TW', 'HK', 'MO', 'MN', 'KZ', 'UZ', 'TM', 'KG', 'TJ', 'AF', 'AZ', 'GE', 'AM'],
    'Oceania': ['AU', 'NZ', 'PG', 'FJ', 'SB', 'VU', 'WS', 'TO', 'KI', 'FM', 'MH', 'PW', 'NR', 'TV', 'CK', 'NU', 'WF', 'PF', 'NC'],
    'Middle East': ['SA', 'AE', 'QA', 'KW', 'BH', 'OM', 'YE', 'IQ', 'IR', 'SY', 'LB', 'JO', 'PS'],
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
                raise ValidationError(f"L'adresse '{rec.email}' est invalide.")

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

    # Protection contre les appels multiples
    scrape_in_progress = fields.Boolean(string="Scraping en cours", default=False)

    # =========================================================================
    # CONFIGURATION LLM - 5 CRITÈRES AVEC POIDS (TOTAL = 100%)
    # =========================================================================
    poids_total = fields.Integer(
        string="Total des poids (%)",
        compute='_compute_poids_total',
        store=False,
    )

    # CRITÈRE 1 : Savoir-faire
    critere_savoir_desc = fields.Text(string="Description")
    critere_savoir_forte = fields.Char(string="Pertinence forte si")
    critere_savoir_poids = fields.Integer(string="Poids (%)", default=20)

    # CRITÈRE 2 : Potentiel client
    critere_potentiel_desc = fields.Text(string="Description")
    critere_potentiel_forte = fields.Char(string="Pertinence forte si")
    critere_potentiel_poids = fields.Integer(string="Poids (%)", default=20)

    # CRITÈRE 3 : CA
    critere_ca_desc = fields.Text(string="Description")
    critere_ca_forte = fields.Char(string="Pertinence forte si")
    critere_ca_poids = fields.Integer(string="Poids (%)", default=20)

    # CRITÈRE 4 : Durée
    critere_duree_desc = fields.Text(string="Description")
    critere_duree_forte = fields.Char(string="Pertinence forte si")
    critere_duree_poids = fields.Integer(string="Poids (%)", default=20)

    # CRITÈRE 5 : Délai
    critere_delai_desc = fields.Text(string="Description")
    critere_delai_forte = fields.Char(string="Pertinence forte si")
    critere_delai_poids = fields.Integer(string="Poids (%)", default=20)

    # =========================================================================
    # MOTS-CLÉS
    # =========================================================================
    keywords_required_ids = fields.Many2many('piste.keyword', string="Mots-clés obligatoires")

    @api.constrains('keywords_required_ids')
    def _check_keywords(self):
        for rec in self:
            if not rec.keywords_required_ids:
                raise ValidationError("Veuillez renseigner au moins un mot-clé.")

    # =========================================================================
    # PLATEFORMES
    # =========================================================================
    platform_achatpublic = fields.Boolean(string="Achatpublic")
    platform_francemarches = fields.Boolean(string="France Marchés")
    platform_awsolutions = fields.Boolean(string="AW Solutions")
    platform_doubletrade = fields.Boolean(string="DoubleTrade")
    platform_marchespublics = fields.Boolean(string="MarchesPublics")
    platform_marchessecurise = fields.Boolean(string="Marchés Sécurisés")
    platform_boamp = fields.Boolean(string="BOAMP")

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
        'res.country', 'piste_source_country_rel',
        'source_id', 'country_id', string="Pays ciblés"
    )

    geo_zone_allowed_country_ids = fields.Many2many(
        'res.country', 'piste_source_allowed_country_rel',
        'source_id', 'country_id',
        string="Pays autorisés",
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
            region_names = [r.country_group_name for r in rec.geo_zone_region_ids if r.country_group_name]
            if not region_names:
                rec.geo_zone_allowed_country_ids = all_countries
                continue
            all_codes = []
            for rname in region_names:
                all_codes += REGION_COUNTRIES.get(rname, [])
            rec.geo_zone_allowed_country_ids = self.env['res.country'].search([
                ('code', 'in', list(set(all_codes)))
            ])

    @api.onchange('geo_zone_region_ids')
    def _onchange_geo_zone_region_ids(self):
        self._compute_geo_zone_allowed_country_ids()
        if self.geo_zones:
            self.geo_zones = self.geo_zones.filtered(lambda c: c in self.geo_zone_allowed_country_ids)

    # =========================================================================
    # GESTION DES POIDS
    # =========================================================================
    @api.depends(
        'critere_savoir_poids', 'critere_potentiel_poids',
        'critere_ca_poids', 'critere_duree_poids', 'critere_delai_poids'
    )
    def _compute_poids_total(self):
        for rec in self:
            rec.poids_total = sum([
                rec.critere_savoir_poids or 0,
                rec.critere_potentiel_poids or 0,
                rec.critere_ca_poids or 0,
                rec.critere_duree_poids or 0,
                rec.critere_delai_poids or 0,
            ])

    @api.constrains(
        'critere_savoir_poids', 'critere_potentiel_poids',
        'critere_ca_poids', 'critere_duree_poids', 'critere_delai_poids'
    )
    def _check_poids_total_100(self):
        for rec in self:
            total = sum([
                rec.critere_savoir_poids or 0,
                rec.critere_potentiel_poids or 0,
                rec.critere_ca_poids or 0,
                rec.critere_duree_poids or 0,
                rec.critere_delai_poids or 0,
            ])
            if total != 100:
                raise ValidationError(
                    f"❌ Le total des poids doit être exactement 100%.\n"
                    f"   Actuellement : {total}%\n\n"
                    f"Veuillez ajuster vos 5 critères."
                )

    # =========================================================================
    # PLANIFICATION
    # =========================================================================
    automation_type = fields.Selection([('manual', 'Manuel'), ('auto', 'Automatique')],
                                       string="Planification", required=True, default='manual')
    
    auto_frequency = fields.Selection([
        ('daily', 'Chaque jour'), ('weekly', 'Chaque semaine'), ('custom', 'Personnalisée'),
    ], string="Fréquence")
    
    auto_date_start = fields.Date(string="Date de début")
    auto_date_end = fields.Date(string="Date de fin")
    auto_time = fields.Selection([  # liste complète des heures
        (f'{h:02d}:00', f'{h:02d}:00') for h in range(24)
    ], string="Heure", default='08:00')
    
    custom_interval = fields.Integer(string="Intervalle", default=1)
    custom_interval_unit = fields.Selection([
        ('hours', 'Heure(s)'), ('days', 'Jour(s)'), ('weeks', 'Semaine(s)'), ('months', 'Mois'),
    ], string="Unité", default='days')

    # =========================================================================
    # NOTIFICATIONS
    # =========================================================================
    notify_odoo = fields.Boolean(string="Notification Odoo", default=True)
    notify_email = fields.Boolean(string="Notification email", default=False)
    notify_email_ids = fields.Many2many('piste.email', string="Destinataires")

    # =========================================================================
    # COMPTEURS
    # =========================================================================
    offer_ids = fields.One2many('piste.offer', 'source_id', string='Offres')
    offer_count = fields.Integer(compute='_compute_offer_count', store=True)
    crm_lead_count = fields.Integer(compute='_compute_crm_lead_count')
    last_search_date = fields.Datetime(string="Dernière recherche")

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
    # CRON METHODS
    # =========================================================================
    def _cron_name(self):
        return f'Veille N8N – {self.name} [{self.id}]'

    def _get_cron_interval(self):
        if self.auto_frequency == 'daily':
            return 1, 'days'
        elif self.auto_frequency == 'weekly':
            return 7, 'days'
        elif self.auto_frequency == 'custom':
            interval = self.custom_interval or 1
            unit = self.custom_interval_unit or 'days'
            if unit == 'weeks':
                interval *= 7
                unit = 'days'
            return interval, unit
        return 1, 'days'

    def _create_or_update_cron(self):
        self.ensure_one()
        if self.automation_type != 'auto':
            self._delete_cron()
            return

        hour = int((self.auto_time or '08:00').split(':')[0])
        nextcall = datetime.combine(
            self.auto_date_start or date.today(), datetime.min.time()
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
            'code': f"model.browse({self.id}).action_run_scrape()",
            'interval_number': interval_number,
            'interval_type': interval_type,
            'nextcall': nextcall,
            'numbercall': -1,
            'active': True,
            'user_id': self.env.ref('base.user_root').id,
        }

        existing = self.env['ir.cron'].sudo().search([('name', '=', self._cron_name())], limit=1)
        if existing:
            existing.sudo().write(cron_vals)
        else:
            self.env['ir.cron'].sudo().create(cron_vals)

    def _delete_cron(self):
        """Désactive le cron au lieu de le supprimer (évite les erreurs de verrou)"""
        cron = self.env['ir.cron'].sudo().search([('name', '=', self._cron_name())], limit=1)
        if cron:
            cron.sudo().write({'active': False})
            _logger.info("✅ Cron désactivé : %s", self._cron_name())

    # =========================================================================
    # OVERRIDES
    # =========================================================================
    def create(self, vals):
        record = super().create(vals)
        record._create_or_update_cron()
        return record

    def write(self, vals):
        res = super().write(vals)
        planning_fields = {'automation_type', 'auto_frequency', 'auto_date_start',
                           'auto_date_end', 'auto_time', 'custom_interval',
                           'custom_interval_unit', 'name'}
        if planning_fields.intersection(vals.keys()):
            for rec in self:
                rec._create_or_update_cron()
        return res

    def unlink(self):
        for rec in self:
            rec._delete_cron()
        return super().unlink()

    # =========================================================================
    # SCRAPING N8N (CORRIGÉ)
    # =========================================================================
    def action_run_scrape(self):
        """Envoie la configuration à N8N avec critères IA"""
        self.ensure_one()

        if self.scrape_in_progress:
            _logger.warning("⚠️ Scraping déjà en cours pour %s", self.name)
            return

        if self.automation_type == 'auto' and self.auto_date_end and date.today() > self.auto_date_end:
            self._delete_cron()
            return

        n8n_webhook_url = "http://localhost:5678/webhook-test/piste-run"  # ← change en prod

        # Préparation des critères IA
        poids_list = [
            self.critere_savoir_poids or 0,
            self.critere_potentiel_poids or 0,
            self.critere_ca_poids or 0,
            self.critere_duree_poids or 0,
            self.critere_delai_poids or 0,
        ]

        criteres_config = [
            (1, 'Savoir-faire / Adéquation métier', self.critere_savoir_desc, self.critere_savoir_forte, poids_list[0]),
            (2, 'Potentiel client / Récurrence', self.critere_potentiel_desc, self.critere_potentiel_forte, poids_list[1]),
            (3, "Chiffre d'affaires", self.critere_ca_desc, self.critere_ca_forte, poids_list[2]),
            (4, 'Durée du projet', self.critere_duree_desc, self.critere_duree_forte, poids_list[3]),
            (5, 'Délai de réponse', self.critere_delai_desc, self.critere_delai_forte, poids_list[4]),
        ]

        criteres_ia = []
        for num, nom, desc, forte, poids in criteres_config:
            if desc or forte:
                criteres_ia.append({
                    'numero': num,
                    'nom': nom,
                    'description': desc or '',
                    'pertinence_forte_si': forte or '',
                    'poids_pourcent': poids,
                })

        payload = {
            'id': self.id,
            'name': self.name,
            'keywords_required': [kw.name for kw in self.keywords_required_ids],
            'platforms': {
                'achatpublic': self.platform_achatpublic,
                'francemarches': self.platform_francemarches,
                'awsolutions': self.platform_awsolutions,
                'doubletrade': self.platform_doubletrade,
                'marchespublics': self.platform_marchespublics,
                'marchessecurise': self.platform_marchessecurise,
                'boamp': self.platform_boamp,
            },
            'budget_min': self.budget_min,
            'budget_max': self.budget_max,
            'geo_zones': [c.code for c in self.geo_zones],
            'geo_regions': [r.name for r in self.geo_zone_region_ids],
            'automation': {
                'type': self.automation_type,
                'frequency': self.auto_frequency,
                'date_start': str(self.auto_date_start) if self.auto_date_start else None,
                'date_end': str(self.auto_date_end) if self.auto_date_end else None,
                'time': self.auto_time,
            },
            'notifications': {
                'odoo': self.notify_odoo,
                'email': self.notify_email,
                'emails_list': [e.email for e in self.notify_email_ids],
            },
            'filtres': {
                'duration_short': self.duration_short,
                'duration_medium': self.duration_medium,
                'duration_long': self.duration_long,
                'client_pme': self.client_pme,
                'client_large': self.client_large,
            },
            'config_ia': {
                'criteres': criteres_ia,
                'poids_total': sum(poids_list),
            } if criteres_ia else None,
            'meta': {
                'description': self.description or '',
                'creator_id': self.create_uid.id if self.create_uid else None,
            }
        }

        self.sudo().write({'scrape_in_progress': True, 'last_search_date': datetime.now()})

        try:
            response = requests.post(
                n8n_webhook_url,
                headers={'Content-Type': 'application/json'},
                json=payload,          # ← recommandé au lieu de data + json.dumps
                timeout=15
            )

            _logger.info("✅ Scrape envoyé : %s → HTTP %s | Response: %s",
                         self.name, response.status_code, response.text[:500])

            if response.status_code >= 400:
                _logger.warning("⚠️ N8N a renvoyé une erreur (HTTP %s): %s",
                                response.status_code, response.text)

            # Notifications
            if self.notify_odoo:
                mots_cles = ', '.join([kw.name for kw in self.keywords_required_ids])
                self.message_post(
                    body=f"✅ Veille <b>{self.name}</b> lancée.<br/>Mots-clés: {mots_cles}",
                    message_type='notification',
                    subtype_xmlid='mail.mt_note',
                )

            if self.notify_email and self.notify_email_ids:
                emails = ','.join(self.notify_email_ids.mapped('email'))
                self.env['mail.mail'].sudo().create({
                    'subject': f'[Veille] {self.name} – lancée',
                    'body_html': f'<p>Veille <b>{self.name}</b> lancée.</p>',
                    'email_to': emails,
                }).send()

        except requests.exceptions.RequestException as e:
            _logger.error("❌ Erreur connexion N8N pour '%s' : %s", self.name, str(e))
            raise ValidationError(f"Impossible de contacter N8N : {str(e)}")
        except Exception as e:
            _logger.error("❌ Erreur inattendue lors du scrape '%s' : %s", self.name, str(e))
            raise ValidationError(f"Erreur inattendue : {str(e)}")
        finally:
            self.sudo().write({'scrape_in_progress': False})

    # =========================================================================
    # ACTIONS VUES
    # =========================================================================
    def name_get(self):
        return [(rec.id, f"Veille – {rec.name}") for rec in self]

    def action_view_offers(self):
        return {
            'type': 'ir.actions.act_window',
            'name': f'Offres – {self.name}',
            'res_model': 'piste.offer',
            'view_mode': 'tree,form',
            'domain': [('source_id', '=', self.id)],
        }

    def action_view_crm_leads(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Pistes – {self.name}',
            'res_model': 'crm.lead',
            'view_mode': 'tree,form,kanban',
            'domain': [('piste_source_id', '=', self.id)],
            'context': {'default_piste_source_id': self.id, 'default_type': 'lead'},
        }