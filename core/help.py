"""
El contenido del Centro de ayuda.

Vive en Python y no en la plantilla por dos razones: se puede probar (que los
enlaces existan, que las secciones de nómina y cobros no se le muestren a
quien no las puede usar) y se lee de corrido cuando haya que corregir un paso.

Cada pregunta describe lo que la aplicación hace de verdad. Si cambia un flujo,
este archivo cambia con él.
"""

#: Secciones del centro de ayuda. `requiere` limita quién la ve:
#: 'admin' = administrador del negocio, 'superuser' = dueño de Kivo.
SECCIONES = [
    {
        'id': 'dinero',
        'titulo': 'Ingresos y egresos',
        'icono': 'fa-money-bill-wave',
        'resumen': 'Registrar la plata que entra y la que sale.',
        'preguntas': [
            {
                'pregunta': '¿Cómo registro un ingreso?',
                'pasos': [
                    'En el menú de la izquierda entra a <strong>Ingresos</strong> y '
                    'oprime <strong>Nuevo ingreso</strong>.',
                    'Escoge la <strong>categoría</strong> (por ejemplo "Ventas en tienda"). '
                    'Solo aparecen las categorías de tipo Ingreso.',
                    'Escribe el <strong>monto</strong>, el <strong>método de pago</strong> y '
                    '<strong>en qué cuenta o caja entró</strong> la plata.',
                    'Pon la <strong>fecha</strong> real del movimiento, no la de hoy, y una '
                    'descripción corta que te sirva para reconocerlo después.',
                    'Guarda. El saldo de esa cuenta sube solo, no hay que tocarlo aparte.',
                ],
                'enlace': ('incomes:income_create', 'Registrar un ingreso'),
            },
            {
                'pregunta': '¿Cómo registro un egreso?',
                'pasos': [
                    'Entra a <strong>Egresos</strong> y oprime <strong>Nuevo egreso</strong>.',
                    'Escoge la categoría (de tipo Egreso), el monto, el método de pago y '
                    'la cuenta o caja de donde salió la plata.',
                    'Guarda. El saldo de esa cuenta baja solo.',
                ],
                'nota': 'Si el monto deja la cuenta en negativo, Kivo no lo guarda y te dice '
                        'cuánto hay disponible. Eso casi siempre significa una de dos: o la '
                        'plata salió de otra cuenta, o el saldo de esa cuenta está desactualizado '
                        'y toca conciliarla.',
                'enlace': ('expenses:expense_create', 'Registrar un egreso'),
            },
            {
                'pregunta': 'Me equivoqué en un registro, ¿lo puedo corregir?',
                'pasos': [
                    'Entra a la lista de Ingresos o Egresos y oprime el registro.',
                    'Usa <strong>Editar</strong> para corregirlo o <strong>Eliminar</strong> '
                    'para borrarlo.',
                    'El saldo de la cuenta se vuelve a calcular solo con el cambio.',
                ],
            },
            {
                'pregunta': 'No me aparece la categoría que necesito',
                'pasos': [
                    'Las categorías tienen tipo: una de <strong>Ingreso</strong> no sale en la '
                    'pantalla de egresos, y al contrario tampoco.',
                    'Si la categoría existe pero no aparece, revisa en '
                    '<strong>Categorías</strong> que esté activa y que sea del tipo correcto.',
                    'Si no existe, créala primero y vuelve al registro.',
                ],
                'enlace': ('core:category_list', 'Ver mis categorías'),
            },
        ],
    },
    {
        'id': 'categorias',
        'titulo': 'Categorías',
        'icono': 'fa-tags',
        'resumen': 'Clasificar el dinero para saber en qué se va.',
        'preguntas': [
            {
                'pregunta': '¿Cómo creo una categoría?',
                'pasos': [
                    'Entra a <strong>Categorías</strong> y oprime '
                    '<strong>Nueva categoría</strong>.',
                    'Escribe el <strong>nombre</strong> y escoge el <strong>tipo</strong>: '
                    'Ingreso o Egreso.',
                    'Guarda. Desde ese momento aparece en los formularios de ese tipo.',
                ],
                'nota': 'Vale más tener pocas categorías claras que muchas parecidas. Si no '
                        'sabes en cuál va un gasto, probablemente sobra una de las dos.',
                'enlace': ('core:category_create', 'Crear una categoría'),
            },
            {
                'pregunta': '¿Puedo borrar una categoría que ya usé?',
                'pasos': [
                    'Puedes intentarlo, pero si tiene ingresos o egresos asociados Kivo la '
                    '<strong>desactiva</strong> en lugar de borrarla y te avisa.',
                    'Así no se pierde el historial: los movimientos viejos siguen mostrando '
                    'su categoría, pero ya no aparece para registros nuevos.',
                ],
            },
        ],
    },
    {
        'id': 'cuentas',
        'titulo': 'Cuentas y caja',
        'icono': 'fa-university',
        'resumen': 'Los bancos y el efectivo, con el saldo real.',
        'preguntas': [
            {
                'pregunta': '¿Cómo agrego una cuenta bancaria?',
                'pasos': [
                    'Entra a <strong>Cuentas y caja</strong> y oprime '
                    '<strong>Nueva cuenta</strong>.',
                    'En <strong>Tipo</strong> escoge <strong>Banco</strong>.',
                    'Ponle un nombre con el que la reconozcas ("Bancolombia ahorros"), el '
                    'banco y el número de cuenta.',
                    'En <strong>Dinero que hay hoy</strong> escribe el saldo que tiene la '
                    'cuenta en este momento.',
                ],
                'enlace': ('bank_accounts:bankaccount_create', 'Crear una cuenta'),
            },
            {
                'pregunta': '¿Cómo agrego la caja del efectivo?',
                'pasos': [
                    'Es la misma pantalla de <strong>Nueva cuenta</strong>, pero en '
                    '<strong>Tipo</strong> escoges <strong>Caja</strong>.',
                    'Puedes tener varias: la del mostrador, la caja fuerte, la de un '
                    'domiciliario.',
                ],
                'nota': 'Cuando se crea el negocio, Kivo ya deja una caja llamada '
                        '"Caja general" para que puedas registrar efectivo desde el primer día.',
            },
            {
                'pregunta': '¿Qué es "Dinero que hay hoy"?',
                'pasos': [
                    'Es el saldo con el que arranca la cuenta en Kivo: lo que tiene en este '
                    'momento en la vida real.',
                    'De ahí en adelante Kivo le suma los ingresos y le resta los egresos que '
                    'registres. No hay que volver a tocarlo.',
                ],
            },
            {
                'pregunta': 'El saldo de Kivo no coincide con el del banco',
                'pasos': [
                    'Entra a la cuenta y oprime <strong>Conciliar</strong>.',
                    'Escribe el <strong>saldo real</strong>, el que muestra el banco o el que '
                    'contaste en la caja.',
                    'Kivo calcula la diferencia y la registra como un ajuste, igual que el '
                    'conteo físico del inventario. Queda la huella de qué se ajustó y cuándo.',
                ],
                'nota': 'Conciliar no borra nada: agrega un movimiento que explica la '
                        'diferencia. Si te descuadra seguido, casi siempre es efectivo que se '
                        'gastó sin registrar.',
                'enlace': ('bank_accounts:bankaccount_list', 'Ver mis cuentas'),
            },
            {
                'pregunta': '¿Por qué no me deja registrar una salida de plata?',
                'pasos': [
                    'Porque esa cuenta no tiene saldo suficiente. Kivo no permite dejar una '
                    'cuenta en negativo: una caja no puede tener menos de cero pesos.',
                    'Revisa si la plata salió de otra cuenta, o concilia la cuenta para '
                    'ponerla al día.',
                ],
            },
        ],
    },
    {
        'id': 'inventario',
        'titulo': 'Inventario',
        'icono': 'fa-box',
        'resumen': 'Productos, bodegas y el movimiento de cada unidad.',
        'preguntas': [
            {
                'pregunta': '¿Cómo creo un producto?',
                'pasos': [
                    'Entra a <strong>Inventario → Productos</strong> y oprime '
                    '<strong>Nuevo producto</strong>.',
                    'Llena el <strong>código (SKU)</strong>, el nombre, la categoría de '
                    'producto y la <strong>unidad de medida</strong>.',
                    'Pon el <strong>precio de compra</strong>, el <strong>precio de venta</strong> '
                    'y el <strong>stock mínimo</strong>.',
                    'Guarda. El producto arranca en cero: el stock entra cuando recibes '
                    'mercancía o cuando registras un conteo.',
                ],
                'nota': 'El stock mínimo es el que dispara las alertas y el reporte de '
                        '"bajo mínimo". Ponle el número con el que alcanzas a reponer sin '
                        'quedarte sin producto.',
                'enlace': ('inventory:product_create', 'Crear un producto'),
            },
            {
                'pregunta': '¿Cómo le entra stock a un producto?',
                'pasos': [
                    'Lo normal es recibiendo mercancía de una <strong>orden de compra</strong>: '
                    'al registrar la recepción, el stock entra solo.',
                    'La otra forma es el <strong>conteo físico</strong>, cuando cuentas lo que '
                    'hay y no coincide con el sistema.',
                ],
                'nota': 'El stock no se edita a mano a propósito. Si se pudiera, el kárdex '
                        'dejaría de explicar por qué hay lo que hay.',
            },
            {
                'pregunta': 'Conté el inventario y no cuadra, ¿cómo lo ajusto?',
                'pasos': [
                    'Entra a <strong>Inventario → Ajustes</strong> (ajuste por conteo físico).',
                    'Escoge el producto y la bodega, y en <strong>Stock contado</strong> '
                    'escribe la cantidad <strong>real</strong> que contaste.',
                    'Escribe el motivo: merma, rotura, producto vencido, error de digitación.',
                    'Kivo calcula la diferencia contra el saldo del sistema y la registra.',
                ],
                'nota': 'No digitas la diferencia, digitas lo que hay. Así no toca hacer '
                        'cuentas mentales ni equivocarse de signo.',
                'enlace': ('inventory:adjustment_create', 'Registrar un conteo'),
            },
            {
                'pregunta': '¿Qué son las bodegas y las unidades de medida?',
                'pasos': [
                    'Las <strong>bodegas</strong> son los sitios donde guardas: la principal, '
                    'la nevera, el punto de venta. Cada movimiento dice de cuál entró o salió.',
                    'Las <strong>unidades de medida</strong> son en qué mides: unidad, libra, '
                    'kilo, caja, litro.',
                    'Al crear el negocio Kivo ya deja una bodega y las unidades más comunes, '
                    'así que puedes empezar sin configurar nada.',
                ],
            },
            {
                'pregunta': '¿Para qué sirve la pantalla de Movimientos?',
                'pasos': [
                    'Es el <strong>kárdex</strong>: la historia de cada entrada y cada salida, '
                    'con la fecha, el motivo, quién la hizo y el saldo que quedó.',
                    'Cuando algo no cuadra, es el primer lugar donde mirar.',
                ],
                'enlace': ('inventory:movement_list', 'Ver movimientos'),
            },
        ],
    },
    {
        'id': 'compras',
        'titulo': 'Compras y proveedores',
        'icono': 'fa-shopping-cart',
        'resumen': 'A quién le compras y cómo entra la mercancía.',
        'preguntas': [
            {
                'pregunta': '¿Cómo ingreso un proveedor?',
                'pasos': [
                    'Entra a <strong>Compras → Proveedores</strong> y oprime '
                    '<strong>Nuevo proveedor</strong>.',
                    'Lo único obligatorio es el <strong>nombre o razón social</strong> y el '
                    '<strong>NIT</strong>.',
                    'Lo demás ayuda cuando toca llamarlo: nombre del contacto, teléfono, '
                    'correo, ciudad y las <strong>condiciones de pago</strong> que tienes con él.',
                ],
                'enlace': ('purchases:supplier_create', 'Crear un proveedor'),
            },
            {
                'pregunta': '¿Cómo hago una orden de compra?',
                'pasos': [
                    'Entra a <strong>Compras → Órdenes de compra</strong> y oprime '
                    '<strong>Nueva orden</strong>.',
                    'Escoge el <strong>proveedor</strong> y la <strong>bodega</strong> donde '
                    'va a llegar la mercancía.',
                    'Agrega una línea por producto: producto, cantidad y precio unitario. '
                    'Puedes agregar tantas líneas como necesites.',
                    'Guarda. La orden queda en <strong>Borrador</strong>, que significa que '
                    'todavía la puedes cambiar.',
                ],
                'enlace': ('purchases:purchaseorder_create', 'Crear una orden'),
            },
            {
                'pregunta': '¿Qué significan los estados de una orden?',
                'pasos': [
                    '<strong>Borrador</strong>: la estás armando, se puede editar.',
                    '<strong>Enviado</strong>: ya se la pasaste al proveedor.',
                    '<strong>Aprobado</strong>: alguien con permiso la autorizó. Solo el '
                    'administrador del negocio puede aprobar.',
                    '<strong>Parcial</strong>: llegó una parte de lo pedido.',
                    '<strong>Recibido</strong>: llegó todo.',
                    '<strong>Cancelado</strong>: se echó para atrás.',
                ],
                'nota': 'Los estados avanzan con los botones de la orden; no se escogen a '
                        'mano de una lista. Así no queda una orden "recibida" sin que haya '
                        'entrado mercancía.',
            },
            {
                'pregunta': '¿Cómo recibo la mercancía que llegó?',
                'pasos': [
                    'Abre la orden y oprime <strong>Registrar recepción</strong>.',
                    'Escribe cuánto llegó <strong>de cada línea</strong>. No tiene que ser '
                    'todo lo pedido.',
                    'Guarda. El stock de esos productos entra solo, con su movimiento en el '
                    'kárdex, y la orden cambia de estado según lo que falte.',
                ],
                'nota': 'Kivo no te deja recibir más de lo que pediste en la línea.',
            },
            {
                'pregunta': 'Llegó menos de lo que pedí, ¿qué hago?',
                'pasos': [
                    'Registra la recepción solo con lo que llegó. La orden queda en '
                    '<strong>Parcial</strong>.',
                    'Cuando llegue el resto, registras otra recepción sobre la misma orden. '
                    'Puedes hacerlo varias veces hasta completar.',
                ],
            },
            {
                'pregunta': '¿Y la factura del proveedor?',
                'pasos': [
                    'En la orden oprime <strong>Registrar factura</strong> y guarda el número, '
                    'la fecha y el valor.',
                    'Sirve para cruzar lo que pediste contra lo que te cobraron.',
                ],
                'enlace': ('purchases:purchaseorder_list', 'Ver mis órdenes'),
            },
        ],
    },
    {
        'id': 'reportes',
        'titulo': 'Reportes',
        'icono': 'fa-chart-bar',
        'resumen': 'Lo que ya registraste, ordenado para decidir.',
        'preguntas': [
            {
                'pregunta': '¿Qué reportes tengo?',
                'pasos': [
                    '<strong>Inventario</strong>: qué se agotó, qué está por debajo del '
                    'mínimo y cuánta plata tienes quieta en mercancía.',
                    '<strong>Compras</strong>: qué compraste, a qué proveedor y cuánto le '
                    'compraste a cada uno.',
                    '<strong>Ingresos y egresos</strong>: cuánto entró, cuánto salió y en qué '
                    'categorías, por periodo.',
                ],
                'enlace': ('reports:home', 'Ir a reportes'),
            },
            {
                'pregunta': '¿Cómo filtro por fechas?',
                'pasos': [
                    'Cada reporte tiene filtros arriba: periodo (hoy, este mes, este año o un '
                    'rango que tú pongas), categoría, proveedor o nivel de stock.',
                    'Los filtros se quedan puestos al cambiar de página, así que puedes '
                    'revisar una lista larga sin perderlos.',
                ],
            },
        ],
    },
    {
        'id': 'nomina',
        'titulo': 'Nómina',
        'icono': 'fa-users',
        'resumen': 'Empleados, liquidación y pago.',
        'requiere': 'admin',
        'preguntas': [
            {
                'pregunta': '¿Cómo agrego un empleado?',
                'pasos': [
                    'Entra a <strong>Nómina → Empleados</strong> y oprime '
                    '<strong>Nuevo empleado</strong>.',
                    'Llena nombres, documento, fecha de ingreso, <strong>cargo</strong>, '
                    '<strong>tipo de contrato</strong> y <strong>salario base</strong> mensual.',
                    'Los datos del banco son opcionales, pero ayudan cuando toca dispersar '
                    'los pagos.',
                ],
                'nota': 'El tipo de contrato decide si ese empleado causa prestaciones '
                        'sociales. Prestación de servicios y aprendizaje no las causan.',
                'enlace': ('payroll:employee_create', 'Crear un empleado'),
            },
            {
                'pregunta': '¿Cómo liquido una quincena o un mes?',
                'pasos': [
                    'Entra a <strong>Nómina → Periodos</strong> y crea uno: nombre, '
                    'frecuencia (semanal, quincenal o mensual), fechas y fecha de pago.',
                    'Abre el periodo y en <strong>1. Liquidar</strong> confirma los días '
                    'trabajados. Kivo liquida a todos los empleados activos.',
                    'Revisa el desprendible de cada uno. Si a alguien le faltaron días u '
                    'horas extra, lo ajustas en su liquidación.',
                    'En <strong>2. Pagar</strong> escoges la cuenta y Kivo registra el egreso '
                    'de la nómina en tus finanzas.',
                    'En <strong>3. Cerrar</strong> congelas el periodo para que nadie lo '
                    'vuelva a tocar.',
                ],
                'enlace': ('payroll:period_list', 'Ver periodos'),
            },
            {
                'pregunta': '¿Cómo cambio lo que se descuenta o se paga?',
                'pasos': [
                    'Entra a <strong>Nómina → Conceptos</strong>. Ahí están salud, pensión, '
                    'auxilio de transporte, horas extra, préstamos y los que agregues.',
                    'De cada uno decides si es ingreso o deducción, cómo se calcula (valor '
                    'fijo, porcentaje del salario o del devengado) y si se aplica a todos '
                    'automáticamente.',
                ],
                'nota': 'Ningún porcentaje está quemado en el programa: si cambia la ley o '
                        'tu acuerdo, lo cambias acá y la próxima liquidación sale con el '
                        'valor nuevo.',
                'enlace': ('payroll:concept_list', 'Ver conceptos'),
            },
            {
                'pregunta': '¿Cómo activo las prestaciones sociales?',
                'pasos': [
                    'Abre el periodo y usa el interruptor '
                    '<strong>¿Usa prestaciones sociales?</strong>.',
                    'Al activarlo, prima, cesantías, intereses y vacaciones se calculan solas '
                    'sobre el devengado.',
                ],
                'nota': 'No se le descuentan al empleado: son costo de la empresa y aparecen '
                        'en un bloque aparte del desprendible. El neto que recibe no cambia.',
            },
        ],
    },
    {
        'id': 'cobros',
        'titulo': 'Cobros y empresas',
        'icono': 'fa-file-invoice-dollar',
        'resumen': 'Administración de Kivo: clientes y sus pagos.',
        'requiere': 'superuser',
        'preguntas': [
            {
                'pregunta': '¿Cómo doy de alta una empresa cliente?',
                'pasos': [
                    'Entra a <strong>Administración Kivo → Empresas</strong> y oprime '
                    '<strong>Nueva empresa</strong>.',
                    'El asistente crea de una vez la empresa, su primer negocio y el usuario '
                    'administrador que va a entrar.',
                    'Al final puedes ponerle el valor de la cuota. Si lo dejas vacío, la '
                    'empresa usa Kivo sin cobro y nunca se bloquea.',
                ],
                'enlace': ('company_create', 'Crear una empresa'),
            },
            {
                'pregunta': '¿Cómo registro que un cliente pagó?',
                'pasos': [
                    'Entra a <strong>Cobros</strong>, abre la empresa y busca la cuota.',
                    'Oprime <strong>Marcar pagada</strong>, pon la fecha, el valor recibido y '
                    'el medio de pago.',
                    'Si estaba bloqueada, el cliente recupera el acceso al instante.',
                ],
                'enlace': ('billing:home', 'Ir a cobros'),
            },
            {
                'pregunta': '¿Cuándo se bloquea un cliente que no paga?',
                'pasos': [
                    'Cuando pasa la fecha de corte de una cuota más los días de gracia del '
                    'plan (5 por defecto).',
                    'Antes de eso el cliente ve un aviso dentro de la aplicación; después '
                    'solo ve la pantalla de cuenta suspendida.',
                    'Su información queda intacta: al registrar el pago vuelve a entrar como '
                    'si nada.',
                ],
                'nota': 'Si a un cliente no le quieres cortar el servicio, apágale '
                        '"Bloquear si no paga" en su plan. Le sigues generando las cuotas, '
                        'pero no se bloquea.',
            },
        ],
    },
    {
        'id': 'cuenta',
        'titulo': 'Usuarios y permisos',
        'icono': 'fa-user-shield',
        'resumen': 'Quién ve qué dentro del negocio.',
        'preguntas': [
            {
                'pregunta': '¿Qué diferencia hay entre administrador y empleado?',
                'pasos': [
                    'El <strong>administrador</strong> del negocio ve todo lo suyo, incluida '
                    'la nómina, y es el único que puede aprobar órdenes de compra.',
                    'El <strong>empleado</strong> registra el día a día pero no ve la nómina '
                    'ni aprueba compras.',
                ],
                'nota': 'Esconder un botón no basta: los permisos se revisan en el servidor, '
                        'así que escribir la dirección a mano tampoco sirve para entrar donde '
                        'no se debe.',
            },
            {
                'pregunta': '¿Otro negocio puede ver mis datos?',
                'pasos': [
                    'No. Todo lo que registras cuelga de tu negocio y las consultas filtran '
                    'por él.',
                    'Dos negocios de la misma empresa tampoco se ven entre ellos.',
                ],
            },
            {
                'pregunta': 'Se me olvidó la contraseña',
                'pasos': [
                    'Por ahora Kivo no tiene recuperación automática por correo: nos escribes '
                    'y te la reiniciamos el mismo día.',
                    'Cuando entres con la clave nueva, cámbiala por una que solo tú sepas y no '
                    'la compartas con el resto del equipo.',
                ],
                'nota': 'Cada persona del negocio debería tener su propio usuario. Compartir '
                        'uno solo se ve práctico hasta el día en que toca saber quién '
                        'registró qué.',
            },
        ],
    },
]


def secciones_para(user):
    """Las secciones que este usuario puede usar de verdad."""
    permitidas = []
    for seccion in SECCIONES:
        requiere = seccion.get('requiere')
        if requiere == 'admin' and getattr(user, 'role', None) != 'admin':
            continue
        if requiere == 'superuser' and not getattr(user, 'is_superuser', False):
            continue
        permitidas.append(seccion)
    return permitidas
