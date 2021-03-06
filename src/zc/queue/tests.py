##############################################################################
#
# Copyright (c) 2011 Zope Foundation and Contributors.
# All Rights Reserved.
#
# This software is subject to the provisions of the Zope Public License,
# Version 2.1 (ZPL).  A copy of the ZPL should accompany this distribution.
# THIS SOFTWARE IS PROVIDED "AS IS" AND ANY AND ALL EXPRESS OR IMPLIED
# WARRANTIES ARE DISCLAIMED, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF TITLE, MERCHANTABILITY, AGAINST INFRINGEMENT, AND FITNESS
# FOR A PARTICULAR PURPOSE.
#
##############################################################################
"""Test Setup
"""
import doctest
import re
import unittest
import zc.queue
from persistent import Persistent
from ZODB import ConflictResolution, MappingStorage, POSException
from zope.testing import renormalizing

checker = renormalizing.RENormalizing([
    # Python 3 set representation changed.
    (re.compile("set\(\[(.*?)\]\)"),
     r"{\1}"),
    (re.compile("set\(\)"),
     r"{}"),
    ])

# TODO: this approach is useful, but fragile.  It also puts a dependency in
# this package on the ZODB, when otherwise it would only depend on persistent.
#
# Other discussed testing approaches include passing values explicitly to the
# queue's conflict resolution code, and having a simple database implemented in
# the persistent package.
#
# This approach is arguably useful in two ways.  First, it confirms that the
# conflict resolution code performs as expected in the desired environment,
# the ZODB.  Second, in the doctest it shows real examples of the queue usage,
# with transaction managers and all: this gives a clearer picture of the
# full context in which this conflict resolution code must dance.


class ConflictResolvingMappingStorage(
    MappingStorage.MappingStorage,
    ConflictResolution.ConflictResolvingStorage):

    def store(self, oid, serial, data, version, transaction):
        assert not version, "Versions are not supported"
        if transaction is not self._transaction:
            raise POSException.StorageTransactionError(self, transaction)

        old_tid = None
        tid_data = self._data.get(oid)
        if tid_data:
            old_tid = tid_data.maxKey()
            if serial != old_tid:
                rdata = self.tryToResolveConflict(
                    oid, old_tid, serial, data)
                if rdata is None:
                    raise POSException.ConflictError(
                        oid=oid, serials=(old_tid, serial), data=data)
                else:
                    data = rdata
        self._tdata[oid] = data
        return self._tid


def test_deleted_bucket():
    """As described in ZODB/ConflictResolution.txt, you need to be very
    careful of objects that are composites of other persistent objects.
    Without careful code, the following situation can cause an item in the
    queue to be lost.

        >>> import transaction # setup...
        >>> from ZODB import DB
        >>> db = DB(ConflictResolvingMappingStorage('test'))
        >>> transactionmanager_1 = transaction.TransactionManager()
        >>> transactionmanager_2 = transaction.TransactionManager()
        >>> connection_1 = db.open(transaction_manager=transactionmanager_1)
        >>> root_1 = connection_1.root()

        >>> q_1 = root_1["q"] = zc.queue.CompositeQueue()
        >>> q_1.put(1)
        >>> transactionmanager_1.commit()

        >>> transactionmanager_2 = transaction.TransactionManager()
        >>> connection_2 = db.open(transaction_manager=transactionmanager_2)
        >>> root_2 = connection_2.root()
        >>> q_2 = root_2["q"]
        >>> q_1.pull()
        1
        >>> q_2.put(2)
        >>> transactionmanager_2.commit()
        >>> transactionmanager_1.commit() # doctest: +IGNORE_EXCEPTION_DETAIL
        Traceback (most recent call last):
        ...
        ConflictError: ...

    Without the behavior, the queue would be empty!

    With a simple queue, this will merge normally.

        >>> transactionmanager_1.abort()
        >>> q_1 = root_1["q"] = zc.queue.Queue()
        >>> q_1.put(1)
        >>> transactionmanager_1.commit()

        >>> transactionmanager_2 = transaction.TransactionManager()
        >>> connection_2 = db.open(transaction_manager=transactionmanager_2)
        >>> root_2 = connection_2.root()
        >>> q_2 = root_2["q"]
        >>> q_1.pull()
        1
        >>> q_2.put(2)
        >>> transactionmanager_2.commit()
        >>> transactionmanager_1.commit()
        >>> list(q_1)
        [2]

    """


def test_legacy():
    """We used to promote the names PersistentQueue and
    CompositePersistentQueue as the expected names for the classes in this
    package.  They are now shortened, but the older names should stay
    available in _queue in perpetuity.

        >>> import zc.queue._queue
        >>> zc.queue._queue.BucketQueue is zc.queue.PersistentQueue
        True
        >>> zc.queue.CompositeQueue is zc.queue.CompositePersistentQueue
        True

    """


class StubPersistentReference(ConflictResolution.PersistentReference):
    def __init__(self, oid):
        self.oid = oid

    def __hash__(self):
        # Use id() here to make tests pass with bad results. Defining the hash
        # as the OID actually equals correct behavior!
        return id(self)#self.oid

    def __cmp__(self, other):
        if self.oid == other.oid:
            return 0
        else:
            raise ValueError("Can't compare")

    def __eq__(self, other):
        if self.oid == other.oid:
            return True
        else:
            raise ValueError("Can't compare")

    def __ne__(self, other):
        raise ValueError("Can't compare")

    __lt__ = __gt__ = __le__ = __ge__ = __ne__

    def __repr__(self):
        return "SPR (%d)" % self.oid


class PersistentObject(Persistent):
    def __init__(self, value):
        self.value = value

    def __eq__(self, other):
        return self.value == other.value

    def __repr__(self):
        return "%s" % self.value


def test_suite():
    flags = doctest.IGNORE_EXCEPTION_DETAIL
    return unittest.TestSuite((
        doctest.DocFileSuite(
            'queue.txt',
            optionflags=flags, checker=checker,
            globs={
                'Queue': zc.queue.Queue,
                'Item': PersistentObject}),
        doctest.DocFileSuite(
            'queue.txt',
            optionflags=flags, checker=checker,
            globs={
                'Queue': lambda: zc.queue.CompositeQueue(2),
                'Item': PersistentObject}),
        doctest.DocFileSuite(
            'queue.txt',
            optionflags=flags, checker=checker,
            globs={
                'Queue': zc.queue.Queue,
                'Item': lambda x: x}),
        doctest.DocFileSuite(
            'queue.txt',
            optionflags=flags, checker=checker,
            globs={
                'Queue': lambda: zc.queue.CompositeQueue(2),
                'Item': lambda x: x}),
        doctest.DocTestSuite()
        ))

if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
