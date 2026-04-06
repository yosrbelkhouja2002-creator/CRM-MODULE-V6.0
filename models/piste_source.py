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
import markupsafe

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
                    f"Le total des poids doit être exactement 100%.\n"
                    f"Actuellement : {total}%\n\n"
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
    auto_time = fields.Selection([
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
        """
        Désactive le cron via SQL direct.
        Contourne le verrou Odoo qui bloque write() pendant l'exécution du cron.
        """
        cron = self.env['ir.cron'].sudo().search([('name', '=', self._cron_name())], limit=1)
        if cron:
            try:
                self.env.cr.execute(
                    "UPDATE ir_cron SET active = false WHERE id = %s",
                    (cron.id,)
                )
                _logger.info("Cron désactivé (SQL) : %s", self._cron_name())
            except Exception as e:
                _logger.warning("Impossible de désactiver le cron '%s' : %s", self._cron_name(), str(e))

    def _disable_orphan_cron(self):
        """
        Désactive les crons orphelins pointant vers cet ID via SQL direct.
        Appelé quand self n'existe plus en base.
        """
        try:
            self.env.cr.execute(
                "UPDATE ir_cron SET active = false WHERE code LIKE %s",
                (f"%model.browse({self.id})%",)
            )
            _logger.info("Cron(s) orphelin(s) désactivé(s) pour piste.source ID %s", self.id)
        except Exception as e:
            _logger.warning("Impossible de désactiver les crons orphelins ID %s : %s", self.id, str(e))

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
    # SCRAPING N8N
    # =========================================================================
    def action_run_scrape(self):
        """Envoie la configuration à N8N avec critères IA et notifications complètes."""
        self.ensure_one()

        # GARDE 1 : l'enregistrement existe-t-il encore ?
        if not self.exists():
            _logger.warning("piste.source(%s) n'existe plus en base — cron orphelin désactivé", self.id)
            self._disable_orphan_cron()
            return

        # GARDE 2 : scraping déjà en cours
        if self.scrape_in_progress:
            _logger.warning("Scraping déjà en cours pour %s", self.name)
            if self.notify_odoo:
                self.message_post(
                    body=markupsafe.Markup(
                        "<b>Scraping ignoré</b> — Un scraping est déjà en cours pour cette veille.<br/>"
                        "Veuillez attendre la fin avant de relancer."
                    ),
                    message_type='notification',
                    subtype_xmlid='mail.mt_note',
                )
            return

        # GARDE 3 : date de fin dépassée
        if self.automation_type == 'auto' and self.auto_date_end and date.today() > self.auto_date_end:
            _logger.info("Date de fin dépassée pour '%s' — cron désactivé", self.name)
            if self.notify_odoo:
                self.message_post(
                    body=markupsafe.Markup(
                        f"<b>Veille terminée</b> — La date de fin "
                        f"(<b>{self.auto_date_end}</b>) est dépassée.<br/>"
                        f"La planification automatique a été désactivée."
                    ),
                    message_type='notification',
                    subtype_xmlid='mail.mt_note',
                )
            self._delete_cron()
            return

        # GARDE 4 : aucun mot-clé configuré
        if not self.keywords_required_ids:
            _logger.error("Aucun mot-clé pour la veille '%s'", self.name)
            if self.notify_odoo:
                self.message_post(
                    body=markupsafe.Markup(
                        "<b>Scraping annulé</b> — Aucun mot-clé configuré sur cette veille.<br/>"
                        "Ajoutez au moins un mot-clé dans l'onglet <b>Mots-clés</b> pour démarrer."
                    ),
                    message_type='notification',
                    subtype_xmlid='mail.mt_note',
                )
            return

        # GARDE 5 : aucune plateforme sélectionnée
        plateformes_actives = [
            label for label, actif in {
                'Achatpublic': self.platform_achatpublic,
                'France Marchés': self.platform_francemarches,
                'AW Solutions': self.platform_awsolutions,
                'DoubleTrade': self.platform_doubletrade,
                'MarchesPublics': self.platform_marchespublics,
                'Marchés Sécurisés': self.platform_marchessecurise,
                'BOAMP': self.platform_boamp,
            }.items() if actif
        ]

        if not plateformes_actives:
            _logger.warning("Aucune plateforme activée pour '%s'", self.name)
            if self.notify_odoo:
                self.message_post(
                    body=markupsafe.Markup(
                        "<b>Scraping annulé</b> — Aucune plateforme sélectionnée.<br/>"
                        "Activez au moins une plateforme dans l'onglet <b>Plateformes</b>."
                    ),
                    message_type='notification',
                    subtype_xmlid='mail.mt_note',
                )
            return

        # N8N webhook URL
        n8n_webhook_url = "http://localhost:5678/webhook-test/piste-run"  # changer en prod

        # Message de démarrage
        mots_cles = ', '.join([kw.name for kw in self.keywords_required_ids])

        if self.notify_odoo:
            self.message_post(
                body=markupsafe.Markup(
                    f"<b>Scraping démarré</b><br/>"
                    f"Mots-clés : <b>{mots_cles}</b><br/>"
                    f"Plateformes : <b>{', '.join(plateformes_actives)}</b>"
                ),
                message_type='notification',
                subtype_xmlid='mail.mt_note',
            )

        # Préparation du payload
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

        criteres_ia = [
            {
                'numero': num,
                'nom': nom,
                'description': desc or '',
                'pertinence_forte_si': forte or '',
                'poids_pourcent': poids,
            }
            for num, nom, desc, forte, poids in criteres_config if desc or forte
        ]

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
                json=payload,
                timeout=15
            )

            _logger.info(
                "Scrape envoyé : %s → HTTP %s | Response: %s",
                self.name, response.status_code, response.text[:500]
            )

            # ERREUR HTTP retournée par N8N
            if response.status_code >= 400:
                error_detail = response.text[:500] if response.text else "Aucun détail"
                _logger.warning(
                    "N8N a renvoyé une erreur (HTTP %s): %s",
                    response.status_code, error_detail
                )
                if self.notify_odoo:
                    self.message_post(
                        body=markupsafe.Markup(
                            f"<b>Erreur N8N</b> (HTTP {response.status_code})<br/>"
                            f"<pre>{error_detail}</pre><br/>"
                            f"<i>Vérifiez que le workflow N8N est bien en mode 'Listen for test event' et que l'URL est correcte.</i>"
                        ),
                        message_type='notification',
                        subtype_xmlid='mail.mt_note',
                    )
                return

            # VÉRIFIER SI LA RÉPONSE EST VIDE
            if not response.text or response.text.strip() == '':
                _logger.warning("Réponse N8N vide")
                if self.notify_odoo:
                    self.message_post(
                        body=markupsafe.Markup(
                            "<b>Réponse N8N vide</b><br/>"
                            "Le webhook a répondu mais sans contenu. Vérifiez votre workflow N8N."
                        ),
                        message_type='notification',
                        subtype_xmlid='mail.mt_note',
                    )
                return

            # ANALYSER LA RÉPONSE JSON
            try:
                resp_json = response.json()
            except json.JSONDecodeError as e:
                _logger.error("Réponse N8N non-JSON : %s", response.text[:500])
                if self.notify_odoo:
                    self.message_post(
                        body=markupsafe.Markup(
                            f"<b>Erreur de format</b><br/>"
                            f"N8N n'a pas renvoyé une réponse JSON valide.<br/>"
                            f"<pre>{response.text[:500]}</pre>"
                        ),
                        message_type='notification',
                        subtype_xmlid='mail.mt_note',
                    )
                return

            # VÉRIFIER SI N8N SIGNALE UNE ERREUR INTERNE
            if isinstance(resp_json, dict) and resp_json.get('error'):
                error_msg = resp_json.get('message', resp_json.get('error', 'Erreur inconnue'))
                _logger.error("N8N a signalé une erreur : %s", error_msg)
                if self.notify_odoo:
                    self.message_post(
                        body=markupsafe.Markup(
                            f"<b>Erreur dans le workflow N8N</b><br/>"
                            f"{error_msg}"
                        ),
                        message_type='notification',
                        subtype_xmlid='mail.mt_note',
                    )
                return

            # VÉRIFIER LES DONNÉES REÇUES
            nb_offres = resp_json.get('total_found', resp_json.get('count', None))
            nb_filtrees = resp_json.get('filtered_out', resp_json.get('filtered_count', None))
            nb_leads = resp_json.get('leads_created', resp_json.get('created_count', None))

            # SI N8N RÉPOND "Workflow was started" = succès asynchrone
            if resp_json.get('message') == 'Workflow was started':
                if self.notify_odoo:
                    self.message_post(
                        body=markupsafe.Markup(
                            f"<b>Scraping lancé avec succès</b><br/>"
                            f"Le workflow N8N a démarré en arrière-plan.<br/>"
                            f"Mots-clés : <b>{mots_cles}</b><br/>"
                            f"Plateformes : <b>{', '.join(plateformes_actives)}</b><br/>"
                            f"<i>Les résultats seront disponibles une fois le traitement terminé.</i>"
                        ),
                        message_type='notification',
                        subtype_xmlid='mail.mt_note',
                    )
                return  # Sortir ici, le workflow tourne en arrière-plan

            # Si données manquantes mais pas "Workflow was started"
            if nb_offres is None and nb_leads is None:
                _logger.warning("Réponse N8N incomplète : %s", resp_json)
                if self.notify_odoo:
                    self.message_post(
                        body=markupsafe.Markup(
                            "<b>Réponse N8N incomplète</b><br/>"
                            "Le workflow n'a pas renvoyé les statistiques attendues.<br/>"
                            f"<pre>{json.dumps(resp_json, indent=2)[:500]}</pre>"
                        ),
                        message_type='notification',
                        subtype_xmlid='mail.mt_note',
                    )
                return

            # SUCCÈS : Afficher les résultats
            if self.notify_odoo:
                self.message_post(
                    body=markupsafe.Markup(
                        f"<b>Scraping terminé avec succès</b><br/>"
                        f"Offres trouvées : <b>{nb_offres if nb_offres is not None else 'N/A'}</b><br/>"
                        f"Filtrées (hors critères) : <b>{nb_filtrees if nb_filtrees is not None else 'N/A'}</b><br/>"
                        f"Leads créés dans le CRM : <b>{nb_leads if nb_leads is not None else 'N/A'}</b>"
                    ),
                    message_type='notification',
                    subtype_xmlid='mail.mt_note',
                )

            # Avertissement si 0 leads créés
            if nb_leads == 0:
                if self.notify_odoo:
                    self.message_post(
                        body=markupsafe.Markup(
                            f"<b>Aucune offre ne correspond aux mots-clés</b> : {mots_cles}<br/>"
                            f"Vérifiez vos critères ou élargissez vos mots-clés."
                        ),
                        message_type='notification',
                        subtype_xmlid='mail.mt_note',
                    )

            # Notification email
            if self.notify_email and self.notify_email_ids:
                emails = ','.join(self.notify_email_ids.mapped('email'))
                self.env['mail.mail'].sudo().create({
                    'subject': f'[Veille] {self.name} – terminée',
                    'body_html': (
                        f'<p>La veille <b>{self.name}</b> s\'est terminée avec succès.</p>'
                        f'<p>Mots-clés : {mots_cles}</p>'
                        f'<p>Plateformes : {", ".join(plateformes_actives)}</p>'
                        f'<p>Résultats : {nb_offres} offres trouvées, {nb_leads} leads créés</p>'
                    ),
                    'email_to': emails,
                }).send()

        # GESTION DES EXCEPTIONS
        except requests.exceptions.ConnectionError:
            _logger.error("Connexion refusée par N8N pour '%s' — URL : %s", self.name, n8n_webhook_url)
            if self.notify_odoo:
                self.message_post(
                    body=markupsafe.Markup(
                        f"<b>Impossible de contacter N8N</b><br/>"
                        f"Vérifiez que N8N est bien démarré à l'adresse :<br/>"
                        f"<code>{n8n_webhook_url}</code>"
                    ),
                    message_type='notification',
                    subtype_xmlid='mail.mt_note',
                )
            raise ValidationError(f"Impossible de contacter N8N (connexion refusée) — {n8n_webhook_url}")

        except requests.exceptions.Timeout:
            _logger.error("Timeout N8N (15s) pour '%s'", self.name)
            if self.notify_odoo:
                self.message_post(
                    body=markupsafe.Markup(
                        "<b>Timeout N8N</b> — Le workflow n'a pas répondu dans les 15 secondes.<br/>"
                        "Le scraping a peut-être quand même démarré côté N8N."
                    ),
                    message_type='notification',
                    subtype_xmlid='mail.mt_note',
                )
            raise ValidationError("Timeout : N8N n'a pas répondu à temps (15s).")

        except requests.exceptions.RequestException as e:
            _logger.error("Erreur réseau N8N pour '%s' : %s", self.name, str(e))
            if self.notify_odoo:
                self.message_post(
                    body=markupsafe.Markup(f"<b>Erreur réseau</b> : {str(e)}"),
                    message_type='notification',
                    subtype_xmlid='mail.mt_note',
                )
            raise ValidationError(f"Impossible de contacter N8N : {str(e)}")

        except Exception as e:
            _logger.error("Erreur inattendue lors du scrape '%s' : %s", self.name, str(e))
            if self.notify_odoo:
                self.message_post(
                    body=markupsafe.Markup(f"<b>Erreur inattendue</b> : {str(e)}"),
                    message_type='notification',
                    subtype_xmlid='mail.mt_note',
                )
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