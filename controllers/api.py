# -*- coding: utf-8 -*-
# =============================================================================
# Module : crm_menu_override
# Fichier : controllers/api.py
# Description : API REST pour la création de leads CRM depuis N8N
#               avec création d'offres piste.offer et attachement PDF.
# =============================================================================

from odoo import http  # type: ignore
from odoo.http import request  # type: ignore
import json
import base64
import logging

_logger = logging.getLogger(__name__)


class CRMAPI(http.Controller):

    # =========================================================================
    # AUTHENTIFICATION VIA API KEY ODOO 17
    # =========================================================================
    def _authenticate_api_key(self):
        """
        Vérifie la clé API dans le header Authorization (Bearer token).
        Utilise le système natif res.users.apikeys d'Odoo 17.
        Retourne (uid, None) si valide, (None, response_erreur) sinon.
        """
        auth_header = request.httprequest.headers.get('Authorization')

        if not auth_header or not auth_header.startswith('Bearer '):
            return None, request.make_response(
                json.dumps({'success': False, 'error': 'Clé API manquante'}),
                headers={'Content-Type': 'application/json'},
                status=401
            )

        key = auth_header.split(' ')[1]

        try:
            uid = request.env['res.users.apikeys']._check_credentials(
                scope='rpc',
                key=key
            )
        except Exception:
            uid = None

        if not uid:
            return None, request.make_response(
                json.dumps({'success': False, 'error': 'Clé API invalide'}),
                headers={'Content-Type': 'application/json'},
                status=401
            )

        return uid, None

    # =========================================================================
    # POST /api/crm/lead/bulk_create
    # Crée des offres piste.offer + leads CRM depuis N8N et attache le PDF
    # =========================================================================
    @http.route(
        '/api/crm/lead/bulk_create',
        type='http',
        auth='none',
        methods=['POST'],
        csrf=False,
        save_session=False
    )
    def bulk_create_leads(self, **kw):
        """
        Reçoit une liste d'offres depuis N8N.
        CRÉE :
        1. Une offre dans piste.offer (visible dans "Pistes trouvées")
        2. Un lead dans crm.lead (avec lien vers l'offre)
        Attache automatiquement le PDF si pdf_base64 est fourni.

        JSON attendu :
        {
            "offers": [
                {
                    "name": "Titre de l'appel d'offre",
                    "contact_name": "IRCEC",
                    "email_from": "...",
                    "piste_source_id": 101,
                    "business_unit_id": 5,      ← optionnel
                    "offre_id": 12,             ← optionnel
                    "sub_offre_id": 45,         ← optionnel
                    "url": "https://...",
                    "description": "...",
                    "website": "https://...",
                    "budget": 50000,
                    "publication_date": "2026-04-05",
                    "pdf_base64": "JVBERi0...", ← optionnel
                    "pdf_filename": "BOAMP.pdf" ← optionnel
                }
            ]
        }
        """
        uid, error_response = self._authenticate_api_key()
        if error_response:
            return error_response

        env = request.env(user=uid)

        try:
            data = json.loads(request.httprequest.data or '{}')
            offers_list = data.get('offers', [])

            if not offers_list:
                return request.make_response(
                    json.dumps({'success': False, 'error': 'Aucune offre fournie'}),
                    headers={'Content-Type': 'application/json'},
                    status=400
                )

            created_leads = []

            for item in offers_list:
                if not item.get('name'):
                    _logger.warning("Offre ignorée : name manquant")
                    continue

                try:
                    # ══════════════════════════════════════════════════════
                    # 1. CRÉER L'OFFRE DANS piste.offer (DIFFÉRÉ)
                    # ══════════════════════════════════════════════════════
                    
                    # Récupérer et valider le source_id
                    piste_source_id = item.get('piste_source_id') or item.get('source_id')
                    
                    if piste_source_id:
                        try:
                            source_id_int = int(piste_source_id)
                            source_exists = env['piste.source'].sudo().browse(source_id_int).exists()
                            if not source_exists:
                                _logger.warning("⚠️ source_id=%s introuvable, création sans source", piste_source_id)
                                piste_source_id = None
                            else:
                                piste_source_id = source_id_int
                        except (ValueError, TypeError):
                            _logger.warning("⚠️ source_id=%s invalide, création sans source", piste_source_id)
                            piste_source_id = None
                    
                    # Préparer les valeurs de l'offre (lead_id sera ajouté après)
                    offer_vals = {
                        'name': item.get('name'),
                        'source_id': piste_source_id,
                        'url': item.get('url'),
                        'description': item.get('description'),
                        'website': item.get('website') or item.get('platform'),
                        'budget': item.get('budget'),
                        'publication_date': item.get('publication_date'),
                        'status': 'new',
                        'notes': item.get('notes') or '',
                    }
                    
                    # Vérifier si l'offre existe déjà
                    if piste_source_id:
                        existing_offer = env['piste.offer'].sudo().search([
                            ('name', '=', item.get('name')),
                            ('source_id', '=', piste_source_id)
                        ], limit=1)
                    else:
                        existing_offer = env['piste.offer'].sudo().search([
                            ('name', '=', item.get('name'))
                        ], limit=1)
                    
                    if existing_offer:
                        offer = existing_offer
                        _logger.info("✓ Offre existante : ID %s", offer.id)
                    else:
                        # Créer l'offre sans lead_id pour l'instant
                        offer = env['piste.offer'].sudo().create(offer_vals)
                        _logger.info("✅ Offre créée : ID %s - %s", offer.id, offer.name)

                    # ══════════════════════════════════════════════════════
                    # 2. CRÉER LE CONTACT SI FOURNI
                    # ══════════════════════════════════════════════════════
                    
                    contact_partner = None
                    if item.get('contact_name') or item.get('email_from'):
                        contact_vals = {
                            'name': item.get('contact_name', 'Contact'),
                            'email': item.get('email_from'),
                            'phone': item.get('phone'),
                            'mobile': item.get('mobile'),
                            'function': item.get('function'),
                            'is_company': False,
                            'type': 'contact',
                        }
                        contact_partner = env['res.partner'].sudo().create(contact_vals)
                        _logger.info("✅ Contact créé : ID %s - %s", contact_partner.id, contact_partner.name)

                    # ══════════════════════════════════════════════════════
                    # 3. CRÉER LE LEAD CRM
                    # ══════════════════════════════════════════════════════
                    
                    lead_vals = {
                        'name': item.get('name'),
                        'type': 'lead',
                        'contact_name': item.get('contact_name'),
                        'email_from': item.get('email_from'),
                        'phone': item.get('phone'),
                        'mobile': item.get('mobile'),
                        'website': item.get('website'),
                        'function': item.get('function'),
                        'email_cc': item.get('email_cc'),
                        'street': item.get('street'),
                        'street2': item.get('street2'),
                        'city': item.get('city'),
                        'zip': item.get('zip'),
                        'user_id': item.get('user_id'),
                        'team_id': item.get('team_id'),
                        'partner_name': item.get('company_name'),
                        'partner_id': item.get('partner_id'),
                        'contact_partner_id': contact_partner.id if contact_partner else item.get('contact_partner_id'),
                        'country_id': item.get('country_id'),
                        'state_id': item.get('state_id'),
                        'business_unit_id': item.get('business_unit_id'),
                        'offre_id': item.get('offre_id'),
                        'sub_offre_id': item.get('sub_offre_id'),
                        'probability': int(item.get('probability', 0)) if item.get('probability') else 0,
                        'expected_revenue': float(item.get('expected_revenue', 0)) if item.get('expected_revenue') else 0,
                        'date_deadline': item.get('date_deadline'),
                        'description': item.get('description'),
                        'Mode_de_livraison': item.get('Mode_de_livraison'),
                        'source_id': item.get('source_id'),
                        'piste_source_id': piste_source_id,
                    }

                    lead = env['crm.lead'].sudo().create(lead_vals)
                    _logger.info("✅ Lead créé : ID %s - %s", lead.id, lead.name)
                    
                    # ══════════════════════════════════════════════════════
                    # 4. LIER L'OFFRE AU LEAD (CORRIGÉ - SQL DIRECT)
                    # ══════════════════════════════════════════════════════
                    
                    if offer and lead:
                        try:
                            # Forcer le flush pour s'assurer que le lead a un ID valide
                            lead.flush_recordset()
                            
                            # Méthode 1: Utiliser write avec flush explicite
                            offer.sudo().write({'lead_id': lead.id})
                            offer.flush_recordset()  # Force l'écriture en DB
                            
                            # Vérification par relecture directe en base
                            env.cr.execute(
                                "SELECT lead_id FROM piste_offer WHERE id = %s", 
                                (offer.id,)
                            )
                            result = env.cr.fetchone()
                            db_lead_id = result[0] if result else None
                            
                            if db_lead_id == lead.id:
                                _logger.info("✅ Offre ID %s liée au Lead ID %s (vérifié en DB)", 
                                            offer.id, lead.id)
                            else:
                                _logger.error("❌ Échec liaison: DB a lead_id=%s, attendu=%s", 
                                             db_lead_id, lead.id)
                                # Tentative avec SQL direct si write échoue
                                env.cr.execute(
                                    "UPDATE piste_offer SET lead_id = %s WHERE id = %s",
                                    (lead.id, offer.id)
                                )
                                _logger.info("✅ Liaison forcée par SQL direct: offre=%s, lead=%s", 
                                            offer.id, lead.id)
                                
                        except Exception as link_error:
                            _logger.error("❌ Erreur liaison offre-lead: %s", str(link_error))
                            # Fallback SQL
                            try:
                                env.cr.execute(
                                    "UPDATE piste_offer SET lead_id = %s WHERE id = %s",
                                    (lead.id, offer.id)
                                )
                                _logger.info("✅ Liaison de secours par SQL: offre=%s, lead=%s", 
                                           offer.id, lead.id)
                            except Exception as sql_error:
                                _logger.error("❌ Échec total liaison: %s", str(sql_error))

                    # ══════════════════════════════════════════════════════
                    # 5. METTRE À JOUR PERTINENCE SI FOURNIE
                    # ══════════════════════════════════════════════════════
                    
                    pertinence = item.get('pertinence')
                    if pertinence:
                        mapping = [
                            ('Savoir-faire / Adéquation métier', 'savoir_faire_resultat', 'savoir_faire_note'),
                            ('Potentiel client / Récurrence', 'potentiel_client_resultat', 'potentiel_client_note'),
                            ("Chiffre d'affaires", 'chiffre_affaires_resultat', 'chiffre_affaires_note'),
                            ('Durée & récurrence du projet', 'duree_recurence_resultat', 'duree_recurence_note'),
                            ('Délai de réponse', 'delai_reponse_resultat', 'delai_reponse_note'),
                        ]
                        for critere_name, res_key, note_key in mapping:
                            line = env['crm.lead.pertinence.line'].sudo().search([
                                ('lead_id', '=', lead.id),
                                ('critere', '=', critere_name),
                            ], limit=1)
                            if line:
                                line.write({
                                    'resultat': pertinence.get(res_key, ''),
                                    'note': float(pertinence.get(note_key, 0) or 0),
                                })

                    # ══════════════════════════════════════════════════════
                    # 6. ATTACHER LE PDF SI FOURNI
                    # ══════════════════════════════════════════════════════
                    
                    pdf_base64 = item.get('pdf_base64')
                    pdf_filename = item.get('pdf_filename', 'document.pdf')

                    pdf_attached = False
                    if pdf_base64 and pdf_base64 not in ('filesystem-v2', '', None):
                        try:
                            env['ir.attachment'].sudo().create({
                                'name': pdf_filename,
                                'type': 'binary',
                                'datas': pdf_base64,
                                'res_model': 'crm.lead',
                                'res_id': lead.id,
                                'mimetype': 'application/pdf',
                            })
                            pdf_attached = True
                            _logger.info("✅ PDF '%s' attaché au lead ID %s", pdf_filename, lead.id)
                        except Exception as pdf_error:
                            _logger.warning("⚠️ Impossible d'attacher le PDF : %s", str(pdf_error))

                    # ══════════════════════════════════════════════════════
                    # 7. PRÉPARER LA RÉPONSE
                    # ══════════════════════════════════════════════════════
                    
                    created_leads.append({
                        'lead_id': lead.id,
                        'offer_id': offer.id,
                        'name': lead.name,
                        'contact_name': lead.contact_name,
                        'contact_id': contact_partner.id if contact_partner else None,
                        'Mode_de_livraison': lead.Mode_de_livraison,
                        'business_unit_id': lead.business_unit_id.id if lead.business_unit_id else None,
                        'business_unit_name': lead.business_unit_id.name if lead.business_unit_id else None,
                        'offre_id': lead.offre_id.id if lead.offre_id else None,
                        'offre_name': lead.offre_id.name if lead.offre_id else None,
                        'sub_offre_id': lead.sub_offre_id.id if lead.sub_offre_id else None,
                        'sub_offre_name': lead.sub_offre_id.name if lead.sub_offre_id else None,
                        'piste_source_id': piste_source_id,
                        'pdf_attached': pdf_attached,
                    })

                except Exception as lead_error:
                    _logger.exception("❌ Erreur création lead/offre : %s", lead_error)
                    continue  # Passe à l'offre suivante au lieu de tout arrêter

            return request.make_response(
                json.dumps({
                    'success': True,
                    'created_count': len(created_leads),
                    'leads': created_leads,
                    'message': f'{len(created_leads)} lead(s) et offre(s) créé(s) avec succès'
                }),
                headers={'Content-Type': 'application/json'},
                status=201
            )

        except Exception as e:
            _logger.exception("❌ Erreur bulk_create_leads")
            return request.make_response(
                json.dumps({'success': False, 'error': str(e)}),
                headers={'Content-Type': 'application/json'},
                status=500
            )

    # =========================================================================
    # POST /api/crm/lead/attach_pdf
    # Attache un PDF en multipart/form-data à un lead existant
    # =========================================================================
    @http.route(
        '/api/crm/lead/attach_pdf',
        type='http',
        auth='none',
        methods=['POST'],
        csrf=False,
        save_session=False
    )
    def attach_pdf(self, **kw):
        """
        Reçoit un PDF en multipart/form-data et l'attache au lead CRM.
        Champs attendus :
            - lead_id  : ID du lead CRM
            - filename : nom du fichier PDF
            - pdf_file : fichier binaire PDF
        """
        uid, error_response = self._authenticate_api_key()
        if error_response:
            return error_response

        env = request.env(user=uid)

        try:
            lead_id = kw.get('lead_id')
            filename = kw.get('filename', 'document.pdf')
            pdf_file = request.httprequest.files.get('pdf_file')

            if not lead_id or not pdf_file:
                return request.make_response(
                    json.dumps({'success': False, 'error': 'lead_id et pdf_file sont obligatoires'}),
                    headers={'Content-Type': 'application/json'},
                    status=400
                )

            lead = env['crm.lead'].sudo().browse(int(lead_id))
            if not lead.exists():
                return request.make_response(
                    json.dumps({'success': False, 'error': f'Lead {lead_id} introuvable'}),
                    headers={'Content-Type': 'application/json'},
                    status=404
                )

            # Encode le fichier binaire en base64
            pdf_data = base64.b64encode(pdf_file.read()).decode('utf-8')

            attachment = env['ir.attachment'].sudo().create({
                'name': filename,
                'type': 'binary',
                'datas': pdf_data,
                'res_model': 'crm.lead',
                'res_id': lead.id,
                'mimetype': 'application/pdf',
            })

            _logger.info("PDF '%s' attaché au lead ID %s", filename, lead.id)
            return request.make_response(
                json.dumps({
                    'success': True,
                    'attachment_id': attachment.id,
                    'lead_id': lead.id,
                    'filename': filename,
                }),
                headers={'Content-Type': 'application/json'},
                status=201
            )

        except Exception as e:
            _logger.exception("Erreur attach_pdf")
            return request.make_response(
                json.dumps({'success': False, 'error': str(e)}),
                headers={'Content-Type': 'application/json'},
                status=500
            )

    # =========================================================================
    # GET /api/crm/lead
    # Retourne la liste de tous les leads CRM
    # =========================================================================
    @http.route(
        '/api/crm/lead',
        type='http',
        auth='none',
        methods=['GET'],
        csrf=False,
        save_session=False
    )
    def get_leads(self, **kw):
        """Retourne la liste complète des leads CRM avec leurs champs principaux."""
        uid, error_response = self._authenticate_api_key()
        if error_response:
            return error_response

        env = request.env(user=uid)

        try:
            leads = env['crm.lead'].sudo().search([])

            leads_data = []
            for lead in leads:
                leads_data.append({
                    'id': lead.id,
                    'name': lead.name,
                    'email_from': lead.email_from,
                    'phone': lead.phone,
                    'contact_name': lead.contact_name,
                    'contact_id': lead.contact_partner_id.id if lead.contact_partner_id else None,
                    'website': lead.website,
                    'partner_id': lead.partner_id.id if lead.partner_id else None,
                    'probability': lead.probability,
                    'expected_revenue': lead.expected_revenue,
                    'user_id': lead.user_id.id if lead.user_id else None,
                    'Mode_de_livraison': lead.Mode_de_livraison,
                    'business_unit_id': lead.business_unit_id.id if lead.business_unit_id else None,
                    'business_unit_name': lead.business_unit_id.name if lead.business_unit_id else None,
                    'offre_id': lead.offre_id.id if lead.offre_id else None,
                    'offre_name': lead.offre_id.name if lead.offre_id else None,
                    'sub_offre_id': lead.sub_offre_id.id if lead.sub_offre_id else None,
                    'sub_offre_name': lead.sub_offre_id.name if lead.sub_offre_id else None,
                    'piste_source_id': lead.piste_source_id.id if lead.piste_source_id else None,
                    'create_date': lead.create_date.isoformat() if lead.create_date else None,
                })

            return request.make_response(
                json.dumps({
                    'success': True,
                    'count': len(leads_data),
                    'leads': leads_data
                }),
                headers={'Content-Type': 'application/json'},
                status=200
            )

        except Exception as e:
            _logger.exception("Erreur get_leads")
            return request.make_response(
                json.dumps({'success': False, 'error': str(e)}),
                headers={'Content-Type': 'application/json'},
                status=500
            )